import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
import scraper as s

class TestV621(unittest.TestCase):
    def test_ebc_article_link(self):
        page='<a href="/fncnews/life/222884">咖啡優惠來了！星巴克買一送一</a>'
        found=s.extract_listing_candidates(page, s.URL_EBC_LIFE_LISTING, 'ebc', 30)
        self.assertEqual(found[0]['url'], 'https://fnc.ebc.net.tw/fncnews/life/222884')

    def test_ebc_in_rss_queries(self):
        self.assertIn('東森財經',s.SOURCE_DISCOVERY_QUERIES)

    def test_negated_app_does_not_override_store(self):
        scope,_=s.detect_channel_scope('門市限定，行動隨時取購買及兌領不適用')
        self.assertEqual(scope,'store')

    def test_positive_app_remains_app(self):
        self.assertEqual(s.detect_channel_scope('APP優惠趣｜11月16日至11月18日')[0],'app')

    def test_og_image_extracted(self):
        soup=BeautifulSoup('<meta property="og:image" content="/images/high-res.jpg">','html.parser')
        self.assertEqual(s.extract_article_image_url(soup,'https://www.nownews.com/news/1'),
                         'https://www.nownews.com/images/high-res.jpg')

    def test_image_url_added_to_dynamic_record(self):
        article={'title':'全家咖啡優惠','url':'https://www.nownews.com/news/6892960'}
        fetched={'ok':True,'final_url':article['url'],'title':article['title'],'published':'2026-11-17',
                 'image_url':'https://example.com/hero.jpg',
                 'lines':['全家','大單品拿鐵買1送1'],
                 'blocks':[{'text':'全家','tag':'h2','strong_texts':[]},
                           {'text':'大單品拿鐵買1送1','tag':'p','strong_texts':[]}]}
        rows=s.extract_article_deals(article,fetched)
        self.assertTrue(rows)
        self.assertTrue(all(x.get('image_url')=='https://example.com/hero.jpg' for x in rows))

    def test_round_robin_orders_sources_before_second_query(self):
        calls=[]
        def fake_rss(q): calls.append(q);return []
        with patch.object(s,'SOURCE_DISCOVERY_QUERIES', {'NOWnews':['N1','N2'],'Yahoo新聞':['Y1'],'東森財經':['E1']}),patch.object(s,'rss',side_effect=fake_rss):
            _,stats=s.discover_source_rss_articles()
        self.assertEqual(calls,['N1','Y1','E1','N2'])
        self.assertEqual(len(stats),3)

    def test_title_only_or_dye_not_promoted(self):
        r=s.make_deal('美吾髮','咖啡栗棕染髮霜買一送一','https://www.nownews.com/news/12','染髮霜買一送一')
        self.assertTrue(s.is_non_offer_record(r))

if __name__=='__main__': unittest.main()
