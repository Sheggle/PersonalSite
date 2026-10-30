import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ripraven.sources import (
    PARTIAL_SOURCE_MARKER,
    AsuraScraper,
    ChapterSource,
    DownloadedChapter,
    MultiSourceScraper,
    SourceUnavailable,
    match_series,
    normalize_title,
    parse_asura_chapter_images,
    parse_asura_chapter_list,
)
from ripraven.web_reader import RipRavenAPI
from ripraven.worker import _one_series


def island(component, props):
    # HTMLParser decodes these attribute entities just as a browser does.
    raw = json.dumps(props).replace('&', '&amp;').replace('"', '&quot;')
    return f'<astro-island component-url="/_astro/{component}.js" props="{raw}"></astro-island>'


def astro(value):
    if isinstance(value, dict):
        return {k: astro(v) for k, v in value.items()}
    if isinstance(value, list):
        return [1, [astro(v) for v in value]]
    return [0, value]


class AsuraParsingTests(unittest.TestCase):
    def test_chapter_list_uses_numbers_and_public_series_url(self):
        html = island('ChapterListReact', astro({'chapters': [
            {'number': 2, 'slug': 'chapter-2'},
            {'number': 1.5, 'slug': 'chapter-1-5'},
            {'number': 1, 'slug': 'chapter-1'},
        ]}))
        chapters = parse_asura_chapter_list(html, 'https://asurascans.com/comics/a-series-id')
        self.assertEqual(chapters, [
            {'number': '2', 'url': 'https://asurascans.com/comics/a-series-id/chapter/2'},
            {'number': '1.5', 'url': 'https://asurascans.com/comics/a-series-id/chapter/1.5'},
            {'number': '1', 'url': 'https://asurascans.com/comics/a-series-id/chapter/1'},
        ])

    def test_reader_pages_stay_in_reading_order(self):
        html = island('ChapterReader', astro({'pages': [
            {'url': 'https://cdn.example/001.webp', 'width': 800},
            {'url': 'https://cdn.example/002.webp', 'width': 800},
            {'url': 'https://cdn.example/003.webp', 'width': 800},
        ]}))
        self.assertEqual(parse_asura_chapter_images(html), [
            'https://cdn.example/001.webp',
            'https://cdn.example/002.webp',
            'https://cdn.example/003.webp',
        ])

    def test_empty_or_malformed_payload_fails_instead_of_marking_complete(self):
        with self.assertRaises(RuntimeError):
            parse_asura_chapter_images(island('ChapterReader', astro({'pages': []})))
        with self.assertRaises(RuntimeError):
            parse_asura_chapter_list('<html></html>', 'https://example/series')

    def test_title_matching_is_exact_but_ignores_punctuation_and_aliases(self):
        candidate = {
            'title': 'The Max-Level Player\'s 100th Regression',
            'alt_titles': ['Another Name'],
        }
        self.assertEqual(normalize_title('Myst_Might, Mayhem'), 'mystmightmayhem')
        self.assertIs(match_series('The Max Level Players 100th Regression', [candidate]), candidate)
        self.assertIs(match_series('Another Name', [candidate]), candidate)
        self.assertIsNone(match_series('Max Level Player', [candidate]))
        self.assertIsNone(match_series('Another Name', [candidate, dict(candidate)]))


class MultiSourceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name) / 'chapter_1'
        self.primary = ChapterSource()
        self.primary.name = 'ravenscans'
        self.primary.fetch_chapter_pages = AsyncMock(
            side_effect=SourceUnavailable('cdn1 unreachable'),
        )
        self.fallback = ChapterSource()
        self.fallback.name = 'asura'
        self.fallback.home = 'https://asurascans.com/'
        self.fallback.find_series = AsyncMock(
            return_value='https://asurascans.com/comics/myst-id',
        )
        self.fallback.scrape_chapter_list = AsyncMock(return_value=[
            {'number': '1.00', 'url': 'https://asurascans.com/comics/myst-id/chapter/1'},
        ])
        self.fallback.fetch_chapter_pages = AsyncMock(return_value=21)
        self.scraper = MultiSourceScraper(self.primary, [self.fallback])
        self.info = {'series_slug': 'myst', 'series_name': 'Myst_Might_Mayhem'}
        self.chapter = {'number': '1', 'url': 'https://raven/chapter-1'}

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_fallback_matches_decimal_chapter_and_replaces_partial_pages(self):
        self.directory.mkdir(parents=True)
        partial = self.directory / 'raven-page.webp'
        partial.write_bytes(b'wrong translation')
        result = await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.assertEqual(result, DownloadedChapter(
            21, 'asura', 'https://asurascans.com/comics/myst-id/chapter/1',
        ))
        self.assertFalse(partial.exists())
        self.fallback.find_series.assert_awaited_once_with('Myst Might Mayhem')
        self.assertIs(self.primary._get_image_sem(), self.fallback._get_image_sem())

    async def test_series_and_chapter_lists_are_cached(self):
        await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.fallback.find_series.assert_awaited_once()
        self.fallback.scrape_chapter_list.assert_awaited_once()

    async def test_manual_override_skips_search(self):
        self.info['source_urls'] = {'asura': '/comics/manual-id'}
        self.fallback.scrape_chapter_list.return_value = [
            {'number': '1', 'url': 'https://asurascans.com/comics/manual-id/chapter/1'},
        ]
        result = await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.assertEqual(result.source, 'asura')
        self.fallback.find_series.assert_not_awaited()
        self.fallback.scrape_chapter_list.assert_awaited_once_with(
            'https://asurascans.com/comics/manual-id',
        )

    async def test_no_fallback_match_preserves_cheap_host_down_skip(self):
        self.fallback.find_series.return_value = None
        with self.assertRaises(SourceUnavailable):
            await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.fallback.fetch_chapter_pages.assert_not_awaited()

    async def test_local_storage_failure_does_not_trigger_fallback(self):
        self.primary.fetch_chapter_pages.side_effect = OSError('disk full')
        with self.assertRaises(OSError):
            await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.fallback.find_series.assert_not_awaited()

    async def test_primary_retry_cleans_partial_fallback_pages(self):
        async def fail_after_page(*_):
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / '001.webp').write_bytes(b'asura')
            raise RuntimeError('asura stopped')

        self.fallback.fetch_chapter_pages.side_effect = fail_after_page
        with self.assertRaises(RuntimeError):
            await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.assertEqual((self.directory / PARTIAL_SOURCE_MARKER).read_text(), 'asura')

        self.primary.fetch_chapter_pages.side_effect = None
        self.primary.fetch_chapter_pages.return_value = 1
        result = await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.assertEqual(result.source, 'ravenscans')
        self.assertFalse((self.directory / '001.webp').exists())
        self.assertEqual((self.directory / PARTIAL_SOURCE_MARKER).read_text(), 'ravenscans')
        self.fallback.fetch_chapter_pages.assert_awaited_once()

    async def test_lookup_error_is_not_cached_as_a_negative_match(self):
        self.fallback.find_series.side_effect = [
            RuntimeError('temporary API failure'),
            'https://asurascans.com/comics/myst-id',
        ]
        with self.assertRaises(SourceUnavailable):
            await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        result = await self.scraper.fetch_chapter_pages(self.chapter, self.info, self.directory)
        self.assertEqual(result.source, 'asura')
        self.assertEqual(self.fallback.find_series.await_count, 2)

    async def test_completion_write_failure_preserves_partial_source(self):
        cache = Mock()
        cache.is_stale.return_value = False
        cache.get_chapters.return_value = [self.chapter]
        original_write_text = Path.write_text

        def fail_completed(path, *args, **kwargs):
            if path.name == 'completed':
                raise OSError('disk full')
            return original_write_text(path, *args, **kwargs)

        with patch.object(Path, 'write_text', fail_completed):
            with self.assertRaises(OSError):
                await _one_series(self.scraper, self.info, cache, Path(self.tmp.name),
                                  lambda *_: False, Mock())
        marker = Path(self.tmp.name) / self.info['series_name'] / 'chapter_1' / PARTIAL_SOURCE_MARKER
        self.assertEqual(marker.read_text(), 'asura')

    async def test_worker_records_source_and_retries_old_raven_failure(self):
        worker_directory = Path(self.tmp.name) / self.info['series_name'] / 'chapter_1'
        worker_directory.mkdir(parents=True)
        (worker_directory / 'failed').write_text(json.dumps({
            'attempts': 2, 'at': time.time(), 'error': 'SourceUnavailable: cdn1 unreachable',
        }))
        (worker_directory / PARTIAL_SOURCE_MARKER).write_text('asura')
        coordinator = Mock()
        coordinator.fetch_chapter_pages = AsyncMock(return_value=DownloadedChapter(
            21, 'asura', 'https://asurascans.com/comics/myst-id/chapter/1',
        ))
        cache = Mock()
        cache.is_stale.return_value = False
        cache.get_chapters.return_value = [self.chapter]
        index = Mock()
        await _one_series(coordinator, self.info, cache, Path(self.tmp.name),
                          lambda *_: False, index)
        completed = json.loads((worker_directory / 'completed').read_text())
        self.assertEqual(completed['source'], 'asura')
        self.assertEqual(completed['source_url'], self.fallback.scrape_chapter_list.return_value[0]['url'])
        self.assertIn('completed_at', completed)
        self.assertFalse((worker_directory / 'failed').exists())
        self.assertFalse((worker_directory / PARTIAL_SOURCE_MARKER).exists())
        index.update_chapter.assert_called_once()


class UserscriptSourceTests(unittest.TestCase):
    def test_full_raven_upload_replaces_partial_fallback_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = RipRavenAPI(downloads_dir=Path(tmp) / 'downloads')
            api.tracking.add('myst', 'Myst_Might_Mayhem', 'https://raven/series', 'https://raven/1')
            chapter_dir = Path(tmp) / 'downloads/Myst_Might_Mayhem/chapter_1'
            chapter_dir.mkdir(parents=True)
            (chapter_dir / '001.webp').write_bytes(b'asura')
            (chapter_dir / PARTIAL_SOURCE_MARKER).write_text('asura')

            app = FastAPI()
            app.include_router(api.router)
            response = TestClient(app).post(
                '/series/myst/chapters/1/pages',
                files=[('pages', ('000.webp', b'raven', 'image/webp'))],
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse((chapter_dir / '001.webp').exists())
            self.assertEqual((chapter_dir / '000.webp').read_bytes(), b'raven')
            self.assertFalse((chapter_dir / PARTIAL_SOURCE_MARKER).exists())
            completed = json.loads((chapter_dir / 'completed').read_text())
            self.assertEqual(completed['source'], 'ravenscans')
            self.assertEqual(completed['via'], 'userscript')

    def test_failed_reupload_invalidates_old_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = RipRavenAPI(downloads_dir=Path(tmp) / 'downloads')
            api.tracking.add('myst', 'Myst_Might_Mayhem', 'https://raven/series', 'https://raven/1')
            chapter_dir = Path(tmp) / 'downloads/Myst_Might_Mayhem/chapter_1'
            chapter_dir.mkdir(parents=True)
            (chapter_dir / 'completed').write_text('old completion')
            app = FastAPI()
            app.include_router(api.router)

            with patch('ripraven.web_reader.clear_partial_images', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    TestClient(app).post(
                        '/series/myst/chapters/1/pages',
                        files=[('pages', ('000.webp', b'raven', 'image/webp'))],
                    )
            self.assertFalse((chapter_dir / 'completed').exists())


if __name__ == '__main__':
    unittest.main()
