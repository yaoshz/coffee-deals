import unittest
from unittest.mock import patch
import requests
import scraper as s


class TestV620(unittest.TestCase):
    def test_undated_rss_title_only_filtered(self):
        row = s.make_deal("全家", "全家咖啡買一送一", "https://www.nownews.com/news/123", "全家咖啡買一送一")
        self.assertTrue(s.is_unsupported_title_only_candidate(row))

    def test_undated_specific_body_offer_not_filtered(self):
        row = s.make_deal("全家", "大單品拿鐵買1送1", "https://www.nownews.com/news/123", "超商優惠全攻略")
        self.assertFalse(s.is_unsupported_title_only_candidate(row))

    def test_undated_official_evergreen_not_filtered(self):
        row = s.make_deal("星巴克", "uniopen 聯名卡買1送1", s.URL_STARBUCKS_UNIOPEN, "uniopen 聯名卡買1送1")
        self.assertFalse(s.is_unsupported_title_only_candidate(row))

    def test_403_fallback_disabled_keeps_requests_response(self):
        resp = requests.Response(); resp.status_code = 403; resp.url = "https://www.ettoday.net/news/20261116/3273004.htm"
        with patch.object(s.requests, "get", return_value=resp), patch.object(s, "ENABLE_SCRAPLING_FALLBACK", False):
            self.assertIs(s.fetch_article_http_response(resp.url), resp)

    def test_404_never_attempts_fallback(self):
        resp = requests.Response(); resp.status_code = 404; resp.url = "https://www.ettoday.net/news/20261116/3273004.htm"
        with patch.object(s.requests, "get", return_value=resp), patch.object(s, "ENABLE_SCRAPLING_FALLBACK", True):
            self.assertIs(s.fetch_article_http_response(resp.url), resp)

    def test_403_non_whitelist_never_attempts_fallback(self):
        resp = requests.Response(); resp.status_code = 403; resp.url = "https://www.nownews.com/news/6892960"
        with patch.object(s.requests, "get", return_value=resp), patch.object(s, "ENABLE_SCRAPLING_FALLBACK", True):
            self.assertIs(s.fetch_article_http_response(resp.url), resp)

if __name__ == "__main__":
    unittest.main()
