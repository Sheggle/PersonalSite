import errno
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

from ripraven.scraper import HOST_DOWN_S, ImageFetchError, RavenScraper, SourceUnavailable
from ripraven.worker import _one_series, chapter_is_shelved


class DownloadRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name) / 'chapter_1'
        self.scraper = RavenScraper()
        self.scraper._get_text = AsyncMock(return_value='ts_reader.run(' + json.dumps({
            'sources': [{'images': ['https://cdn.example/0.jpg', 'https://cdn.example/1.jpg']}]
        }) + ');')

    async def asyncTearDown(self):
        await self.scraper.close()
        self.tmp.cleanup()

    def transport(self, handler):
        self.scraper._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fetch(self):
        with patch('ripraven.scraper.IMAGE_ATTEMPTS', 1):
            return await self.scraper.fetch_chapter_pages('https://example/chapter-1/', self.directory)

    async def test_outage_skips_host_then_recovers(self):
        self.transport(lambda request: httpx.Response(522, request=request))
        with self.assertRaises(ImageFetchError):
            await self.fetch()
        with self.assertRaises(SourceUnavailable):
            await self.fetch()
        self.scraper._host_down['cdn.example'] = time.time() - HOST_DOWN_S - 1
        await self.scraper.close()
        self.transport(lambda request: httpx.Response(200, content=b'page', request=request))
        self.assertEqual(await self.fetch(), 2)
        self.assertFalse(self.scraper._host_down)

    async def test_missing_image_does_not_blacklist_host(self):
        self.transport(lambda request: httpx.Response(404, request=request))
        with self.assertRaises(ImageFetchError):
            await self.fetch()
        self.assertFalse(self.scraper._host_down)

    async def test_partial_success_does_not_blacklist_host(self):
        def handler(request):
            if request.url.path == '/1.jpg':
                raise httpx.ReadTimeout('', request=request)
            return httpx.Response(200, content=b'page', request=request)
        self.transport(handler)
        with self.assertRaises(ImageFetchError):
            await self.fetch()
        self.assertFalse(self.scraper._host_down)
        self.assertEqual((self.directory / '0.jpg').read_bytes(), b'page')

    async def test_disk_failure_leaves_no_partial_image_or_host_blacklist(self):
        self.transport(lambda request: httpx.Response(200, content=b'page', request=request))
        original_write = Path.write_bytes

        def fail_write(path, data):
            original_write(path, data[:1])
            raise OSError(errno.ENOSPC, 'No space left on device')

        with patch.object(Path, 'write_bytes', fail_write):
            with self.assertRaises(OSError):
                await self.fetch()
        self.assertFalse(self.scraper._host_down)
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertEqual(await self.fetch(), 2)
        self.assertEqual((self.directory / '0.jpg').read_bytes(), b'page')

    async def test_worker_surfaces_storage_failure_without_shelving(self):
        cache = Mock()
        cache.is_stale.return_value = False
        cache.get_chapters.return_value = [{'number': '1', 'url': 'https://example/chapter-1/'}]
        self.scraper.fetch_chapter_pages = AsyncMock(side_effect=OSError(errno.ENOSPC, 'disk full'))
        with self.assertRaises(OSError):
            await _one_series(self.scraper, {'series_name': 'Series'}, cache,
                              Path(self.tmp.name), lambda *_: False, Mock())
        self.assertFalse((Path(self.tmp.name) / 'Series/chapter_1/failed').exists())

    async def test_skipped_chapter_retries_when_host_cooldown_ends(self):
        self.directory.mkdir()
        marker = self.directory / 'failed'
        marker.write_text(json.dumps({'attempts': 10, 'at': time.time(),
                                      'error': 'SourceUnavailable: cdn.example unreachable'}))
        self.assertTrue(chapter_is_shelved(self.directory))
        record = json.loads(marker.read_text())
        record['at'] -= HOST_DOWN_S + 1
        marker.write_text(json.dumps(record))
        self.assertFalse(chapter_is_shelved(self.directory))
        record['error'] = 'ImageFetchError: ReadTimeout'
        marker.write_text(json.dumps(record))
        self.assertTrue(chapter_is_shelved(self.directory))


if __name__ == '__main__':
    unittest.main()
