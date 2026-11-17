#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6.18 發現層與解析層回歸測試；全部離線執行。"""
import os
import sys
import unittest
from unittest.mock import patch
from datetime import date
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scraper


class V618DateRegressionTests(unittest.TestCase):
    def setUp(self):
        self.old_today = scraper.TODAY
        scraper.TODAY = date(2026, 11, 12)

    def tearDown(self):
        scraper.TODAY = self.old_today

    def test_711_brand_is_not_a_date(self):
        self.assertEqual(scraper.date_context("7-11 濃萃美式買2送2"), (None, None, ""))
        self.assertEqual(scraper.date_context("7－11 門市咖啡優惠"), (None, None, ""))

    def test_iso_date_with_year_still_works(self):
        start, end, text = scraper.date_context("活動期間 2026-11-13～2026-11-17")
        self.assertEqual(start, date(2026, 11, 13))
        self.assertEqual(end, date(2026, 11, 17))
        self.assertTrue(text)

    def test_slash_and_chinese_dates_still_work(self):
        self.assertEqual(scraper.date_context("11/13 限定優惠")[0], date(2026, 11, 13))
        self.assertEqual(scraper.date_context("11月13日限定")[0], date(2026, 11, 13))


class V618DiscoveryTests(unittest.TestCase):
    def test_nownews_listing_depth_and_url(self):
        self.assertEqual(scraper.URL_NOWNEWS_LISTING, "https://www.nownews.com/cat/life/")
        self.assertEqual(scraper.URL_NOWNEWS_CONSUMER_LISTING, "https://www.nownews.com/cat/life/smart-life/")
        listing = [(key, url, limit) for key, url, limit in [
            ("nownews", scraper.URL_NOWNEWS_LISTING, 30),
            ("nownews_consumption", scraper.URL_NOWNEWS_CONSUMER_LISTING, 30),
            ("tvbs", scraper.URL_TVBS_LISTING, 30),
        ]]
        self.assertEqual(listing[0][2], 30)
        self.assertEqual(listing[1][1], "https://www.nownews.com/cat/life/smart-life/")
        self.assertEqual(listing[2][1], "https://news.tvbs.com.tw/life")

    def test_tvbs_listing_extracts_article_direct_url(self):
        html = '''<html><body><article><a href="/life/4047065">超商雙11咖啡優惠 全家買一送一</a></article></body></html>'''
        found = scraper.extract_listing_candidates(html, scraper.URL_TVBS_LISTING, "tvbs", 30)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["url"], "https://news.tvbs.com.tw/life/4047065")

    def test_nownews_listing_extracts_article_direct_url(self):
        html = '''<html><body><article><a href="/news/6891616">全家咖啡優惠、7-11買一送一</a></article></body></html>'''
        found = scraper.extract_listing_candidates(html, scraper.URL_NOWNEWS_LISTING, "nownews", 30)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["url"], "https://www.nownews.com/news/6891616")

    def test_direct_media_url_is_not_sent_to_google_decoder(self):
        url, method = scraper.resolve_google_news_url("https://www.nownews.com/news/6891616")
        self.assertEqual(url, "https://www.nownews.com/news/6891616")
        self.assertEqual(method, "direct")

    def test_applealmond_native_rss_discovers_direct_article_urls(self):
        xml = '''<?xml version="1.0"?><rss><channel>
          <item><title>本週咖啡優惠與超商寄杯整理</title><link>https://applealmond.com/posts/999001</link><pubDate>Thu, 12 Nov 2026 08:00:00 +0800</pubDate></item>
          <item><title>iPhone 新功能教學</title><link>https://applealmond.com/posts/999002</link></item>
        </channel></rss>'''.encode("utf-8")
        response = SimpleNamespace(content=xml, ok=True)
        response.raise_for_status = lambda: None
        with patch.object(scraper.requests, "get", return_value=response):
            articles, stats = scraper.discover_native_rss_articles()
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["url"], "https://applealmond.com/posts/999001")
        self.assertTrue(stats["蘋果仁"]["ok"])

    def test_google_news_url_detection(self):
        self.assertTrue(scraper.is_google_news_url("https://news.google.com/rss/articles/CBMiTEST"))
        self.assertFalse(scraper.is_google_news_url("https://www.tvbs.com.tw/life/4047065"))

    def test_google_news_decoder_returns_real_publisher_url(self):
        import types
        fake_module = types.SimpleNamespace(gnewsdecoder=lambda url, interval=1: {
            "status": True, "decoded_url": "https://news.tvbs.com.tw/life/4047065"
        })
        with patch.dict(sys.modules, {"googlenewsdecoder": fake_module}):
            decoded, method = scraper.resolve_google_news_url("https://news.google.com/rss/articles/CBMiTEST")
        self.assertEqual(decoded, "https://news.tvbs.com.tw/life/4047065")
        self.assertEqual(method, "googlenewsdecoder")


    def test_google_news_rss_filters_irrelevant_titles_before_decode(self):
        import xml.etree.ElementTree as ET
        rss_xml = ET.Element("rss")
        channel = ET.SubElement(rss_xml, "channel")
        for title, link in [
            ("政治即時新聞", "https://news.google.com/rss/articles/CBMiPOLITICS"),
            ("全家咖啡買一送一優惠", "https://news.google.com/rss/articles/CBMiCOFFEE"),
        ]:
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = title
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "pubDate").text = "Thu, 12 Nov 2026 08:00:00 +0800"
        response = SimpleNamespace(content=ET.tostring(rss_xml), ok=True)
        response.raise_for_status = lambda: None
        fake_module = SimpleNamespace(gnewsdecoder=lambda urls, interval=1: [
            {"success": True, "decoded_url": "https://news.example/family-coffee"}
        ])
        scraper.GOOGLE_NEWS_DECODE_BUDGET_REMAINING = 40
        with patch.object(scraper.requests, "get", return_value=response), \
             patch.dict(sys.modules, {"googlenewsdecoder": fake_module}):
            found = scraper.rss("全家咖啡優惠")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["url"], "https://news.example/family-coffee")
        self.assertEqual(scraper.GOOGLE_NEWS_DECODE_BUDGET_REMAINING, 39)

    def test_google_news_decode_has_per_query_and_run_caps(self):
        import xml.etree.ElementTree as ET
        rss_xml = ET.Element("rss")
        channel = ET.SubElement(rss_xml, "channel")
        for i in range(20):
            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = f"超商咖啡優惠買一送一第{i}則"
            ET.SubElement(item, "link").text = f"https://news.google.com/rss/articles/CBMi{i}"
            ET.SubElement(item, "pubDate").text = "Thu, 12 Nov 2026 08:00:00 +0800"
        response = SimpleNamespace(content=ET.tostring(rss_xml), ok=True)
        response.raise_for_status = lambda: None
        decoded_calls = []
        def fake_decoder(urls, interval=1):
            decoded_calls.extend(urls)
            return [{"success": True, "decoded_url": f"https://news.example/{i}"} for i, _ in enumerate(urls)]
        fake_module = SimpleNamespace(gnewsdecoder=fake_decoder)
        scraper.GOOGLE_NEWS_DECODE_BUDGET_REMAINING = 40
        with patch.object(scraper.requests, "get", return_value=response), \
             patch.dict(sys.modules, {"googlenewsdecoder": fake_module}):
            found = scraper.rss("超商咖啡優惠")
        self.assertEqual(len(decoded_calls), scraper.MAX_GOOGLE_NEWS_DECODE_PER_QUERY)
        self.assertEqual(len(found), scraper.MAX_GOOGLE_NEWS_DECODE_PER_QUERY)
        scraper.GOOGLE_NEWS_DECODE_BUDGET_REMAINING = 2
        with patch.object(scraper.requests, "get", return_value=response), \
             patch.dict(sys.modules, {"googlenewsdecoder": fake_module}):
            found = scraper.rss("超商咖啡優惠")
        self.assertEqual(len(found), 2)
        self.assertEqual(scraper.GOOGLE_NEWS_DECODE_BUDGET_REMAINING, 0)

    def test_google_news_batch_decoder_uses_publisher_urls(self):
        import types
        fake_module = types.SimpleNamespace(gnewsdecoder=lambda urls, interval=1: [
            {"success": True, "decoded_url": "https://news.tvbs.com.tw/life/4047065"},
            {"success": True, "decoded_url": "https://www.nownews.com/news/6891616"},
        ])
        google_urls = [
            "https://news.google.com/rss/articles/CBMiTVBS",
            "https://news.google.com/rss/articles/CBMiNOW",
        ]
        with patch.dict(sys.modules, {"googlenewsdecoder": fake_module}):
            result = scraper.resolve_google_news_urls(google_urls)
        self.assertEqual(result[google_urls[0]][0], "https://news.tvbs.com.tw/life/4047065")
        self.assertEqual(result[google_urls[1]][0], "https://www.nownews.com/news/6891616")


class V618StaleArticleTests(unittest.TestCase):
    def setUp(self):
        self.old_today = scraper.TODAY
        scraper.TODAY = date(2026, 11, 12)

    def tearDown(self):
        scraper.TODAY = self.old_today

    def test_recent_same_url_is_rescanned_but_old_known_url_is_skipped(self):
        snapshot = {"deals": [{
            "store": "全家", "offer": "美式買一送一", "article_url": "https://news.example/old",
            "source_urls": ["https://news.example/old"], "end_date": "2026-11-30", "status": "active"
        }]}
        candidates = [
            {"url": "https://news.example/old", "published": "2026-11-01"},
            {"url": "https://news.example/old", "published": "2026-11-11"},
            {"url": "https://news.example/new", "published": "2026-11-01"},
        ]
        kept, skipped = scraper.filter_known_stale_articles(candidates, snapshot, rescan_days=3)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["published"], "2026-11-11")


class V618ContentDedupTests(unittest.TestCase):
    def test_same_offer_line_in_two_brand_sections_is_preserved(self):
        html = '''<!doctype html><html><head><meta property="og:title" content="咖啡優惠整理"></head>
        <body><article>
          <h2>7-ELEVEN</h2><p>特大杯美式買1送1</p>
          <h2>全家</h2><p>特大杯美式買1送1</p>
        </article></body></html>'''
        response = SimpleNamespace(content=html.encode("utf-8"), url="https://example.com/article", ok=True)
        response.raise_for_status = lambda: None
        with patch.object(scraper.requests, "get", return_value=response):
            result = scraper.fetch_article({"url": "https://example.com/article", "title": "咖啡優惠整理"})
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["lines"].count("特大杯美式買1送1"), 2)
        block_texts = [block["text"] for block in result["blocks"]]
        self.assertGreaterEqual(block_texts.count("特大杯美式買1送1"), 2)
        scoped = scraper.scope_article_blocks(result["blocks"])
        scoped_matches = [x for x in scoped if x["text"] == "特大杯美式買1送1"]
        self.assertEqual([x["brand"] for x in scoped_matches], ["7-ELEVEN", "全家"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
