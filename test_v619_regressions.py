#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v6.19 structural regressions, using synthetic HTML patterns (not downloaded source snapshots)."""
import unittest
from datetime import date
from unittest.mock import patch
from types import SimpleNamespace
import scraper
from bs4 import BeautifulSoup

NOWNEWS_LAYOUT = '''<html><body><article><h1>本週咖啡優惠</h1><p>
🟡LINE禮物（7-11電子票券）<br>◾大杯美式買1送1<br>
🟡7-ELEVEN<br>📍門市｜11月13日至11月17日<br>◾特大杯美式2杯95元<br>
🟡全家便利商店<br>📍APP優惠趣｜11月16日至11月18日<br>◾大單品拿鐵買1送1<br>
🟡萊爾富<br>◾特大杯特濃拿鐵買1送1<br>
🟡美廉社<br>◾大杯美式咖啡買5送5<br>
🟡全聯福利中心<br>◾OFF COFFEE咖啡14杯369元
</p></article></body></html>'''
COSMO_LAYOUT = '''<html><body><main><article><h1>全家咖啡買一送一 11月17日</h1>
<h2>大單品美式</h2><p>■ 活動時間：11/16-11/18</p><p>■ 買一送一</p>
<h2>大單品拿鐵</h2><p>■ 活動時間：11/16-11/18</p><p>■ 買一送一</p>
</article></main></body></html>'''

class NewListingTests(unittest.TestCase):
    def test_cosmopolitan_direct_link(self):
        page = '<a href="/tw/lifestyle/hot-topics/g74434865/family-mart-1117/">全家大單品美式買1送1優惠</a>'
        out = scraper.extract_listing_candidates(page, scraper.URL_COSMO_LISTING, "cosmo", 30)
        self.assertEqual(len(out), 1)
        self.assertIn('g74434865',out[0]['url'])

    def test_ettoday_direct_link(self):
        page = '<a href="/news/20261116/3273004.htm">全家咖啡優惠與7-ELEVEN買一送一</a>'
        out = scraper.extract_listing_candidates(page, scraper.URL_ETTODAY_LISTING, "ettoday", 30)
        self.assertEqual(len(out), 1)

    def test_starbucks_direct_link(self):
        page = '<a href="/stores/allevent/show.jspx?n=1234">星巴克買一送一門市活動優惠</a>'
        out = scraper.extract_listing_candidates(page, scraper.URL_STARBUCKS_EVENTS, "starbucks", 30)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['brand_hints'], ['星巴克'])

class SectionScopeTests(unittest.TestCase):
    def setUp(self):
        self.old = scraper.TODAY
        scraper.TODAY = date(2026,11,17)
    def tearDown(self):
        scraper.TODAY = self.old

    def test_br_and_emoji_scopes(self):
        blocks = scraper.extract_dom_article_blocks(BeautifulSoup(NOWNEWS_LAYOUT, 'html.parser'))
        scoped = scraper.scope_article_blocks(blocks)
        mapping = {x['text']:x for x in scoped}
        self.assertEqual(mapping['大杯美式買1送1']['brand'],'7-ELEVEN')
        self.assertEqual(mapping['特大杯美式2杯95元']['channel_scope'],'store')
        self.assertEqual(mapping['大單品拿鐵買1送1']['brand'],'全家')
        self.assertEqual(mapping['大單品拿鐵買1送1']['channel_scope'],'app')
        self.assertEqual(mapping['OFF COFFEE咖啡14杯369元']['brand'],'全聯')

    def test_three_bullet_styles_and_paired_drinks(self):
        self.assertEqual(scraper.identify_block_brand('★全家')[0],'全家')
        self.assertEqual(scraper.identify_block_brand('🟡全家便利商店')[0],'全家')
        self.assertEqual(scraper.identify_block_brand('🟡全聯福利中心')[0],'全聯')
        line = "Let's Café大單品美式、大單品拿鐵買1送1"
        self.assertEqual(scraper.split_compound_offer(line),[line])

    def test_mock_fetch_nownews_preserves_br(self):
        response=SimpleNamespace(content=NOWNEWS_LAYOUT.encode(), url='https://www.nownews.com/news/6892960')
        response.raise_for_status=lambda:None
        with patch.object(scraper.requests,'get',return_value=response):
            fetched=scraper.fetch_article({'url':response.url,'published':'2026-11-17'})
        self.assertTrue(fetched['ok'])
        offers=scraper.extract_article_deals({'url':response.url,'published':'2026-11-17'}, fetched)
        brands={x['store'] for x in offers}
        self.assertTrue({'7-ELEVEN','全家','萊爾富','美廉社','全聯'}.issubset(brands),brands)

    def test_cosmo_listicle_product_date_offer(self):
        response=SimpleNamespace(content=COSMO_LAYOUT.encode(), url='https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74434865/family-mart-1117/')
        response.raise_for_status=lambda:None
        with patch.object(scraper.requests,'get',return_value=response):
            fetched=scraper.fetch_article({'url':response.url,'published':'2026-11-17'})
        self.assertTrue(fetched['ok'])
        offers=scraper.extract_article_deals({'url':response.url,'published':'2026-11-17'}, fetched)
        names=' '.join(x['offer'] for x in offers)
        self.assertIn('大單品美式', names)
        self.assertIn('大單品拿鐵', names)
        self.assertTrue(any(x['start_date']=='2026-11-16' and x['end_date']=='2026-11-18' for x in offers),offers)

if __name__=='__main__':unittest.main()
