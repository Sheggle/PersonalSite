import html
import json
import unittest

from ripraven.pattern_finder import parse_source_url
from ripraven.scraper import parse_asura_chapter_images, parse_asura_chapter_list


def island(component: str, props: dict) -> str:
    return (f'<astro-island uid="x" component-url="/_astro/{component}.Ab12.js" '
            f'props="{html.escape(json.dumps(props))}" client="load"></astro-island>')


class SourceUrlTests(unittest.TestCase):
    def test_ravenscans_chapter_and_series(self):
        chapter = parse_source_url('https://ravenscans.org/city-of-sins-chapter-1-1/')
        series = parse_source_url('https://ravenscans.org/manga/city-of-sins/')
        self.assertEqual(chapter['chapter_num'], '1.1')
        self.assertIsNone(series['chapter_num'])
        for parsed in (chapter, series):
            self.assertEqual(parsed['series_name'], 'City_Of_Sins')
            self.assertEqual(parsed['series_url'], 'https://ravenscans.org/manga/city-of-sins/')

    def test_asura_chapter_and_series(self):
        base = 'https://asurascans.com/comics/damn-reincarnation-7de80a82'
        chapter = parse_source_url(base + '/chapter/1#resume')
        series = parse_source_url(base)
        self.assertEqual(chapter['chapter_num'], '1')
        self.assertIsNone(series['chapter_num'])
        for parsed in (chapter, series):
            self.assertEqual(parsed['series_slug'], 'damn-reincarnation')
            self.assertEqual(parsed['series_name'], 'Damn_Reincarnation')
            self.assertEqual(parsed['series_url'], base)

    def test_other_urls_are_rejected(self):
        self.assertIsNone(parse_source_url('https://ravenscans.org/'))
        self.assertIsNone(parse_source_url('https://asurascans.com/browse'))


class AsuraPageTests(unittest.TestCase):
    def test_chapter_list(self):
        page = island('ChapterListReact', {'chapters': [1, [
            [0, {'number': [0, 2], 'slug': [0, 'chapter-2']}],
            [0, {'number': [0, 1.5], 'slug': [0, 'chapter-1-5']}],
        ]]})
        base = 'https://asurascans.com/comics/x-7de80a82'
        self.assertEqual(parse_asura_chapter_list(page, base), [
            {'number': '2', 'url': base + '/chapter/2'},
            {'number': '1.5', 'url': base + '/chapter/1.5'},
        ])

    def test_chapter_images(self):
        page = island('ChapterReader', {'isLocked': [0, False], 'pages': [1, [
            [0, {'url': [0, 'https://cdn.asurascans.com/a/1/001.webp?v=1'], 'width': [0, 760]}],
            [0, {'url': [0, 'https://cdn.asurascans.com/a/1/002.webp?v=1'], 'width': [0, 760]}],
        ]]})
        self.assertEqual(parse_asura_chapter_images(page), [
            'https://cdn.asurascans.com/a/1/001.webp?v=1',
            'https://cdn.asurascans.com/a/1/002.webp?v=1',
        ])

    def test_locked_chapter_raises(self):
        page = island('ChapterReader', {'isLocked': [0, True], 'pages': [1, []]})
        with self.assertRaisesRegex(RuntimeError, 'locked'):
            parse_asura_chapter_images(page)


if __name__ == '__main__':
    unittest.main()
