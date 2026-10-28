import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from ripraven.scraper import RavenScraper


class CloudflareClearanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scraper = RavenScraper()

    async def asyncTearDown(self):
        await self.scraper.close()

    def challenge(self, request):
        return httpx.Response(
            403,
            headers={'cf-mitigated': 'challenge'},
            text='<title>Just a moment...</title>',
            request=request,
        )

    async def test_clearance_is_shared_by_concurrent_series(self):
        def handler(request):
            if 'cf_clearance=cleared' in request.headers.get('cookie', ''):
                return httpx.Response(200, text='series page', request=request)
            return self.challenge(request)

        self.scraper._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clearance = AsyncMock(return_value=(
            'cleared page', 'Chrome test', [{
                'name': 'cf_clearance', 'value': 'cleared',
                'domain': '.ravenscans.org', 'path': '/',
            }],
        ))
        with patch('ripraven.scraper.fetch_with_clearance', clearance):
            pages = await asyncio.gather(*(
                self.scraper._get_text(f'https://ravenscans.org/manga/series-{i}/')
                for i in range(3)
            ))

        self.assertEqual(pages, ['cleared page', 'series page', 'series page'])
        self.assertEqual(clearance.await_count, 1)
        self.assertEqual(self.scraper._client.headers['User-Agent'], 'Chrome test')

    async def test_plain_403_does_not_launch_browser(self):
        self.scraper._client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(403, text='no', request=request),
            ),
        )
        clearance = AsyncMock()
        with patch('ripraven.scraper.fetch_with_clearance', clearance):
            with self.assertRaises(httpx.HTTPStatusError):
                await self.scraper._get_text('https://ravenscans.org/manga/private/')
        clearance.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
