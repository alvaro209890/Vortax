import unittest
from services.web_feeds import feed_entries, feed_text


class FeedTests(unittest.TestCase):
    def test_rss_keeps_article_url_date_and_publisher(self):
        rows = feed_entries('<rss><channel><item><title>IA &amp; trabalho</title><link>https://news.example/article</link><pubDate>Fri, 09 Oct 2026 10:00:00 GMT</pubDate><source url="https://publisher.example">Fonte</source><description>&lt;b&gt;Resumo&lt;/b&gt;</description></item></channel></rss>')
        self.assertEqual(rows[0]["title"], "IA & trabalho")
        self.assertEqual(rows[0]["publisher_url"], "https://publisher.example")
        self.assertIn("09 Oct 2026", feed_text(rows))
        self.assertIn("https://news.example/article", feed_text(rows))
        self.assertNotIn("<b>", rows[0]["snippet"])

    def test_atom_and_invalid_links(self):
        rows = feed_entries('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Publicação</title><link href="https://example.com/post"/><updated>2026-10-09</updated></entry><entry><link href="javascript:alert(1)"/></entry></feed>')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["published"], "2026-10-09")
        self.assertEqual(feed_entries("not XML"), [])
