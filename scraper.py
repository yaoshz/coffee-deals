#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""省咖啡｜優惠雷達

目標：
- 抓取固定指定文章 + Google News RSS 發現的近期文章。
- 優先讀取 JSON-LD articleBody、文章正文、段落、清單與標題。
- 一篇文章可拆出多筆優惠，支援段落日期上下文、民國年與西元年。
- 將使用者已提供且可辨識的 Yahoo／中天優惠以結構化資料保底，避免網站封鎖時漏掉已知資訊。
- 去除圖片說明、導覽文字與明顯重複；資料日期不足時標示 verify，不自行猜日期。
- 若大多數來源抓取失敗，保留舊 deals.json，避免網路問題清空網站。

提醒：任何爬蟲都不能保證完整抓到所有媒體的即時內容。部分網站會擋自動請求，
因此本程式的固定已知優惠會保留，並提供 RSS 搜尋與失敗保護；每筆仍應回原文核對。
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "deals.json")
MAX_ARTICLES = 120
REQUEST_DELAY_SECONDS = 0.25
REQUEST_TIMEOUT = 22
MIN_SUCCESSFUL_ARTICLES_TO_REPLACE = 1

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    "Cache-Control": "no-cache",
}

URL_CTINEWS = "https://ctinews.com/news/items/bKxrXQKYW9"
URL_APPLE_329785 = "https://applealmond.com/posts/329785"
URL_APPLE_329295 = "https://applealmond.com/posts/329295"
URL_APPLE_328076 = "https://applealmond.com/posts/328076"
URL_YAHOO_GENERAL = (
    "https://tw.news.yahoo.com/4%E5%A4%A7%E8%B6%85%E5%95%86%E5%85%89%E5%BE%A9%E7%AF%80%E9%80%A3%E5%81%87-"
    "%E5%92%96%E5%95%A1%E8%B2%B71%E9%80%811-%E7%8F%8D%E5%A5%B610%E6%9D%AF360%E5%85%83-"
    "%E9%9C%9C%E6%B7%87%E6%B7%8B-%E6%9E%9C%E6%98%94%E5%8A%A0%E5%85%A5%E5%84%AA%E6%83%A0-014400310.html"
)
URL_YAHOO_TYPHOON = (
    "https://tw.stock.yahoo.com/news/%E9%A2%B1%E9%A2%A8%E5%81%87%E5%92%96%E5%95%A1%E5%84%AA%E6%83%A0-"
    "%E8%90%8A%E7%88%BE%E5%AF%8C-%E8%B2%B7-%E9%80%81-7-043900203.html"
)
URL_NOWNEWS = "https://www.nownews.com/news/6884698"
URL_COSMO = "https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74211453/hilife-coffee-1022/"

SEED_ARTICLES = [
    {"title": "Yahoo 新聞｜四大超商光復節連假咖啡優惠", "url": URL_YAHOO_GENERAL, "published": "2026-10-22"},
    {"title": "中天新聞｜超商咖啡優惠整理", "url": URL_CTINEWS, "published": "2026-10-22"},
    {"title": "蘋果仁｜2026 光復節超商咖啡優惠懶人包", "url": URL_APPLE_329785, "published": "2026-10-22"},
    {"title": "Yahoo 新聞｜颱風假咖啡優惠、萊爾富買一送一、7-11 美式 2 杯 66 元", "url": URL_YAHOO_TYPHOON, "published": ""},
    {"title": "蘋果仁｜2026 本週咖啡優惠 10/19～10/25", "url": URL_APPLE_329295, "published": "2026-10-19"},
    {"title": "蘋果仁｜2026 雙十國慶咖啡優惠懶人包", "url": URL_APPLE_328076, "published": ""},
    {"title": "NOWnews｜本週咖啡優惠", "url": URL_NOWNEWS, "published": ""},
    {"title": "Cosmopolitan Taiwan｜萊爾富咖啡優惠", "url": URL_COSMO, "published": "2026-10-22"},
]

RSS_QUERIES = [
    '台灣 超商咖啡優惠 2026 10月 11月 買一送一',
    '7-ELEVEN CITY CAFE 咖啡優惠 寄杯 2026 10月 11月',
    '全家 Let’s Café Let’s Tea 咖啡優惠 2026 10月 11月',
    '萊爾富 Hi-Life Hi Café 咖啡優惠 買一送一 2026',
    'OKmart OKCAFE 咖啡優惠 2026 10月',
    '美廉社 咖啡優惠 2026 10月 11月',
    '星巴克 路易莎 cama 85度C 咖啡優惠 2026 10月',
    'site:applealmond.com/posts 本週咖啡優惠 2026',
    'site:tw.news.yahoo.com 超商 咖啡優惠 2026',
    'site:tw.stock.yahoo.com/news 颱風假 咖啡優惠 萊爾富',
    'site:ctinews.com/news/items 咖啡優惠 寄杯',
    'site:nownews.com 超商咖啡優惠 2026',
    'site:cosmopolitan.com/tw/lifestyle/hot-topics 咖啡優惠 萊爾富',
]

STORE_PATTERNS = [
    ("7-ELEVEN", re.compile(r"7\s*[-－]?\s*ELEVEN|7\s*[-－]?\s*11|CITY\s*CAFE|CITY\s*TEA|CITY\s*PEARL|CITY\s*PRIMA|OPENPOINT", re.I)),
    ("全家", re.compile(r"全家|Let['’]?s\s*Caf[eé]|Let['’]?s\s*Tea|Fami!?ce", re.I)),
    ("萊爾富", re.compile(r"萊爾富|Hi\s*[- ]?Life|Hi\s*Cafe", re.I)),
    ("OKmart", re.compile(r"OKmart|OK\s*超商|OKCAFE", re.I)),
    ("美廉社", re.compile(r"美廉社", re.I)),
    ("小北百貨", re.compile(r"小北百貨|SHOWBA\s*Caf[eé]", re.I)),
    ("星巴克", re.compile(r"星巴克|Starbucks", re.I)),
    ("路易莎", re.compile(r"路易莎|LOUISA", re.I)),
    ("85°C", re.compile(r"85\s*°?\s*C", re.I)),
    ("cama", re.compile(r"\bcama\b", re.I)),
    ("全聯", re.compile(r"全聯|大全聯", re.I)),
]

OFFER_RE = re.compile(
    r"買\s*[一1]\s*送\s*[一1]|買\s*\d+\s*送\s*\d+|買\s*\d+\s*送\s*[一1]"
    r"|第\s*[二2]\s*杯|第二杯|任選\s*\d+\s*杯|\d+\s*杯.{0,24}\d[\d,]*\s*元"
    r"|\d[\d,]*\s*杯\s*\d[\d,]*\s*元|寄杯|折\s*扣|打\s*\d+\s*折|\d+\s*折"
    r"|優惠價|組合價|現折|折價|均一價|單杯\s*\d+\s*元|\d+\s*元.{0,12}(多一杯|多1杯)"
    r"|咖啡.{0,30}\d[\d,]*\s*元|大杯.{0,30}\d[\d,]*\s*元|免費|咖啡日|限量\d*萬組",
    re.I,
)

DATE_RANGE_RE = re.compile(
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
    r"\s*(?:至|到|～|~|－|—|–|-|起至)\s*"
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
)
SINGLE_DATE_RE = re.compile(r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?")


def canonical_url(url: str) -> str:
    """移除 Yahoo/Google 追蹤 query，讓同一篇文章只抓一次。"""
    try:
        p = urlparse((url or "").strip())
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in {"guccounter", "guce_referrer", "guce_referrer_sig", "utm_source", "utm_medium", "utm_campaign"}]
        path = p.path.rstrip("/") or "/"
        return urlunparse((p.scheme or "https", p.netloc.lower(), path, "", urlencode(query), ""))
    except Exception:
        return (url or "").strip()


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(s or ""))).strip()


def normalize_offer(s: str) -> str:
    s = normalize_space(s).lower().replace("let’s", "let's")
    s = re.sub(r"圖\s*[／/]\s*[^，。；]*", "", s)
    s = re.sub(r"[\s　，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", s)
    return s


def make_date(year, month, day, fallback_year=None):
    try:
        if year:
            y = int(year)
            if y < 1912:
                y += 1911
        else:
            y = int(fallback_year or TODAY.year)
        return date(y, int(month), int(day))
    except (ValueError, TypeError, OverflowError):
        return None


def parse_published(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(TZ)
        return dt.date()
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo:
            dt = dt.astimezone(TZ)
        return dt.date()
    except Exception:
        return None


def date_context(text: str, published: str = ""):
    """回傳 start/end/date_text。只有截止日或缺日期時不憑空推算活動起日。"""
    pub_day = parse_published(published)
    fallback_year = (pub_day or TODAY).year
    m = DATE_RANGE_RE.search(text or "")
    if m:
        y1, mo1, d1, y2, mo2, d2 = m.groups()
        start = make_date(y1, mo1, d1, fallback_year)
        end = make_date(y2 or y1, mo2, d2, (start.year if start else fallback_year))
        if start and end:
            if not y1 and not y2 and end < start and start.month >= 10 and end.month <= 3:
                end = date(start.year + 1, end.month, end.day)
            if end < start and not (not y1 and not y2 and start.month >= 10 and end.month <= 3):
                return None, None, "日期範圍疑似錯誤，請查原文"
            return start, end, m.group(0)

    # 「即日起至 115/11/10」等：有發稿日才以發稿日當開始日；否則留待確認。
    if "即日起" in (text or ""):
        cutoff = re.search(r"即日起\s*(?:至|到|～|~|-)?\s*((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)", text)
        if cutoff:
            sm = SINGLE_DATE_RE.search(cutoff.group(1))
            if sm:
                y, mo, d = sm.groups()
                end = make_date(y, mo, d, fallback_year)
                start = pub_day
                if start and end and end >= start:
                    return start, end, cutoff.group(0)
                return None, end, cutoff.group(0)

    # 只有截止日：不把整段發布日誤當活動開始日。
    cutoff = re.search(
        r"(?:至|到|截止(?:日期)?(?:為|：|:)?|限定至|活動至)\s*"
        r"((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)", text or ""
    )
    if cutoff:
        sm = SINGLE_DATE_RE.search(cutoff.group(1))
        if sm:
            y, mo, d = sm.groups()
            return None, make_date(y, mo, d, fallback_year), sm.group(0)
    return None, None, ""


def infer_status(start: str, end: str) -> str:
    try:
        s = date.fromisoformat(start) if start else None
        e = date.fromisoformat(end) if end else None
    except ValueError:
        return "verify"
    if e and e < TODAY:
        return "expired"
    if s and e:
        if s > TODAY:
            return "upcoming"
        if s <= TODAY <= e:
            return "active"
    return "verify"


def make_deal(store, offer, url, title, start="", end="", date_text="", published="", needs_check=True, category="coffee"):
    url = canonical_url(url)
    return {
        "store": store or "品牌待確認",
        "offer": normalize_space(offer),
        "status": infer_status(start, end),
        "start_date": start or "",
        "end_date": end or "",
        "date_text": date_text or (f"{start} ～ {end}" if start and end else "活動日期尚待確認"),
        "article_title": title or "優惠文章",
        "article_url": url,
        "source_urls": [url] if url else [],
        "published": published or "",
        "source": "人工整理／新聞文章自動擷取",
        "needs_check": bool(needs_check),
        "category": category,
    }


def curated_deals():
    """使用者貼文已能確認的優惠保底資料。期限依原文；日期未知者保持待確認。"""
    out = []
    def add(store, offer, url, title, start="", end="", dt="", published="", category="coffee"):
        out.append(make_deal(store, offer, url, title, start, end, dt, published, True, category))

    # 中天：使用者明確指定應保留的優惠。第一組品牌在貼出的片段中不明，故不猜品牌。
    ctit = "快來喝！超商咖啡寄杯買30送30　限今天加10元多1杯｜中天新聞網"
    add("品牌待確認", "大杯美式 7 杯組 255 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("品牌待確認", "大杯拿鐵 7 杯組 310 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("品牌待確認", "黑糖珍珠撞奶／珍珠奶茶 7 杯組 315 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("全家", "Let's Tea 任選第二杯 8 折；商品依店舖實際供應為準，數量有限，售完為止。", URL_CTINEWS, ctit, "2026-10-22", "2026-11-10", "即日起～115/11/10（依原文）", "2026-10-22")
    # 中天現有文字中提到、但使用者提供的片段未附完整日期的組合。
    add("品牌待確認", "17 杯濃萃美式 500 元（店家與活動日期請查原文）", URL_CTINEWS, ctit)
    add("品牌待確認", "17 杯拿鐵 700 元（店家與活動日期請查原文）", URL_CTINEWS, ctit)
    add("品牌待確認", "17 杯重乳拿鐵 850 元（店家與活動日期請查原文）", URL_CTINEWS, ctit)

    # Yahoo 新聞：2026 光復節連假優惠。出版日期依使用者貼文標示 2026-10-22。
    yt = "4大超商光復節連假「咖啡買1送1、珍奶10杯360元」霜淇淋、果昔加入優惠"
    pub = "2026-10-22"
    s22, e31, d22 = "2026-10-22", "2026-10-31", "10/22～10/31"
    s25, e25, d25 = "2026-10-25", "2026-10-31", "10/25～10/31"
    add("7-ELEVEN", "CITY CAFE 特大杯美式 10 杯組 360 元（限量 10 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY CAFE 特大杯拿鐵 10 杯組 480 元（限量 10 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY PRIMA 中杯冰精品香椰厚拿鐵／精品冰燕麥拿鐵任選 10 杯組 600 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY TEA 香鑽水果茶 10 杯組 450 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY PEARL 咖啡珍珠歐蕾 10 杯組 500 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY PEARL 黑糖珍珠撞奶／珍珠奶茶任選 10 杯組 360 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s22, e31, d22, pub)
    add("7-ELEVEN", "CITY CAFE 大杯燕麥拿鐵 6 杯 333 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s25, e25, d25, pub)
    add("7-ELEVEN", "CITY CAFE 指定熱飲任選 7 杯 333 元：香草焦糖風味瑪奇朵、黃金榛果太妃、皇家醇濃伯爵紅茶、靜岡濃抹茶、鹿兒島濃焙茶、好時經典可可（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s25, e25, d25, pub)
    add("7-ELEVEN", "CITY TEA 一顆檸檬青茶／一顆檸檬紅茶／青梅冰茶任選 9 杯 333 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s25, e25, d25, pub)
    add("7-ELEVEN", "CITY TEA 冰淇淋紅茶 8 杯 333 元（限量 5 萬組）", URL_YAHOO_GENERAL, yt, s25, e25, d25, pub)
    add("7-ELEVEN", "CITY TEA 黃金蕎麥奶茶／黃金蕎麥茶任選 7 杯 333 元（限量 5 萬組；原文註明全台販售）", URL_YAHOO_GENERAL, yt, s25, e25, d25, pub)

    add("全家", "Let's Café 大杯特濃美式／拿鐵同品項買 2 送 2", URL_YAHOO_GENERAL, yt, "2026-10-23", "2026-10-27", "10/23～10/27", pub)
    add("全家", "Let's Tea 厚濃抹茶拿鐵同品項買 2 送 2", URL_YAHOO_GENERAL, yt, "2026-10-23", "2026-10-27", "10/23～10/27", pub)
    add("全家", "Fami!ce 霜淇淋 2 支 55 元", URL_YAHOO_GENERAL, yt, "2026-10-23", "2026-10-27", "10/23～10/27", pub, category="related")

    add("萊爾富", "特大美式／特大特濃美式／特大重乳拿鐵／大杯燕麥奶拿鐵，同品項買 1 送 1", URL_YAHOO_GENERAL, yt, "2026-10-14", "2026-11-10", "10/14～11/10", pub)
    add("萊爾富", "大杯拿鐵全系列第二杯 5 元（燕麥奶拿鐵除外）", URL_YAHOO_GENERAL, yt, "2026-10-14", "2026-11-10", "10/14～11/10", pub)
    add("萊爾富", "Happy Hour：每週六、日 10:00～14:00，大杯美式／大杯拿鐵單杯 29 元（原文列活動期間 10/14～11/10）", URL_YAHOO_GENERAL, yt, "2026-10-14", "2026-11-10", "10/14～11/10；每週六日 10:00～14:00", pub)
    add("萊爾富", "Hi-Life VIP APP 整買零取：大杯美式／大杯重乳拿鐵／台茶18紅玉拿鐵，同品項買 10 送 10；每會員限購 2 組", URL_YAHOO_GENERAL, yt, "2026-10-24", "2026-10-31", "10/24～10/31", pub)
    add("萊爾富", "Hi-Life VIP APP 整買零取：大杯特濃美式／大杯特濃拿鐵同品項買 30 送 30", URL_YAHOO_GENERAL, yt, "2026-10-14", "2026-11-10", "10/14～11/10", pub)
    add("萊爾富", "果昔全系列均一價 69 元（不含芋頭戀乳、芋仔憨吉）", URL_YAHOO_GENERAL, yt, "2026-10-14", "2026-11-10", "10/14～11/10", pub, category="related")

    add("OKmart", "週年慶多款商品第 2 件 6 折起；是否適用咖啡品項須以店家活動規則確認", URL_YAHOO_GENERAL, yt, "2026-10-22", "2026-11-24", "即日起～11/24；咖啡適用未確認", pub, category="related")
    add("美廉社", "美廉社 APP 隨買隨取：大杯濃萃美式咖啡 100 杯 2,000 元", URL_YAHOO_GENERAL, yt, "2026-10-22", "2026-10-27", "即日起～10/27", pub)
    add("美廉社", "美廉社 APP 隨買隨取：大杯濃萃鮮奶拿鐵 100 杯 2,400 元", URL_YAHOO_GENERAL, yt, "2026-10-22", "2026-10-27", "即日起～10/27", pub)
    add("小北百貨", "SHOWBA Café 光復節活動：10/25 大杯美式／拿鐵買 1 送 1", URL_YAHOO_GENERAL, yt, "2026-10-25", "2026-10-25", "2026/10/25 光復節", pub)
    add("小北百貨", "SHOWBA Café 會員日：每週三大杯美式／拿鐵買 1 送 1（常態週期；實際日期與門市請查公告）", URL_YAHOO_GENERAL, yt, dt="每週三會員日；期限未明", published=pub)
    add("小北百貨", "SHOWBA Café 平日大杯咖啡 7 折常駐優惠（實際適用品項／門市請查公告）", URL_YAHOO_GENERAL, yt, dt="常駐優惠；期限未明", published=pub)

    # Yahoo 股市／新聞另一篇：標題明確列出的優惠，正文日期未提供則待確認。
    ytt = "颱風假咖啡優惠：萊爾富買一送一、7-11 美式 2 杯 66 元"
    add("萊爾富", "指定咖啡買 1 送 1（依文章標題，品項與活動日期待查原文）", URL_YAHOO_TYPHOON, ytt)
    add("7-ELEVEN", "美式咖啡 2 杯 66 元（依文章標題，杯型與活動日期待查原文）", URL_YAHOO_TYPHOON, ytt)

    return out


def rss(query: str):
    url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    results = []
    for item in root.findall(".//item"):
        title = normalize_space(item.findtext("title") or "")
        link = canonical_url(item.findtext("link") or "")
        published = item.findtext("pubDate") or ""
        if link:
            results.append({"title": title, "url": link, "published": published})
    return results


def parse_jsonld_article_bodies(soup):
    bodies = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        stack = obj if isinstance(obj, list) else [obj]
        while stack:
            item = stack.pop(0)
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("@graph"), list):
                stack.extend(item["@graph"])
            typ = item.get("@type", "")
            types = typ if isinstance(typ, list) else [typ]
            if any(str(t).lower() in {"article", "newsarticle", "reportagenewsarticle", "blogposting"} for t in types):
                body = item.get("articleBody") or item.get("description")
                if isinstance(body, str) and len(body) > 80:
                    bodies.append(body)
                headline = item.get("headline")
                if headline and not bodies:
                    bodies.append(str(headline))
    return bodies


def split_text_to_lines(text: str):
    text = html.unescape(str(text or "")).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    raw_parts = re.split(r"[\r\n]+|(?<=[。！？])\s*|(?<=；)\s*|(?<=;)", text)
    lines = []
    for part in raw_parts:
        line = normalize_space(part).strip(" •◾▪●　\t\u200b")
        if len(line) < 3 or len(line) > 1200:
            continue
        if line not in lines:
            lines.append(line)
    return lines


def fetch_article(article):
    """取得文章文字。先讀 JSON-LD，再找文章正文/段落；記錄抓取成功與否。"""
    url = canonical_url(article.get("url", ""))
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        final_url = canonical_url(response.url)
        soup = BeautifulSoup(response.content, "html.parser")

        title = (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
        if not title:
            meta = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
            title = normalize_space(meta.get("content", "")) if meta else article.get("title", "")
        published = article.get("published", "")
        for attrs in ({"property": "article:published_time"}, {"name": "pubdate"}, {"name": "date"}, {"itemprop": "datePublished"}):
            meta = soup.find("meta", attrs=attrs)
            if meta and meta.get("content"):
                published = meta["content"]
                break

        lines = []
        # 先解析 JSON-LD，避免移除 script 時一併丟掉內文。
        for body in parse_jsonld_article_bodies(soup):
            lines.extend(split_text_to_lines(body))

        roots = []
        for selector in [
            '[itemprop="articleBody"]', "article", ".article-body", ".articleBody",
            ".entry-content", ".post-content", ".article-content", ".story-content",
            "main"
        ]:
            roots.extend(soup.select(selector))
        if not roots and soup.body:
            roots = [soup.body]
        seen_roots = set()
        for root in roots:
            marker = id(root)
            if marker in seen_roots:
                continue
            seen_roots.add(marker)
            for node in root.select("h1,h2,h3,h4,p,li,td,th,figcaption,blockquote"):
                txt = normalize_space(node.get_text(" ", strip=True))
                if txt:
                    lines.extend(split_text_to_lines(txt))
            if not lines:
                lines.extend(split_text_to_lines(root.get_text("\n", strip=True)))

        # 排除容易造成誤判的導覽/圖片說明，並保持原文次序去重。
        clean = []
        seen = set()
        for line in lines:
            line = strip_caption(normalize_space(line))
            key = re.sub(r"\W", "", line.lower())
            if not key or key in seen or is_noise(line):
                continue
            seen.add(key)
            clean.append(line)
        ok = len(clean) >= 3 and any(is_coffee_related(x) for x in [title, *clean])
        logging.info("FETCH %s (%s): %s lines", "OK" if ok else "LOW CONTENT", final_url, len(clean))
        if not ok:
            return {"ok": False, "url": url, "final_url": final_url, "title": title, "published": published, "lines": []}
        return {"ok": True, "url": url, "final_url": final_url, "title": title or article.get("title", ""), "published": published, "lines": clean}
    except Exception as exc:
        logging.warning("FETCH ERROR %s: %s", url, exc)
        return {"ok": False, "url": url, "final_url": url, "title": article.get("title", ""), "published": article.get("published", ""), "lines": []}


def strip_caption(line: str) -> str:
    """刪除混在優惠句尾的圖片來源文字，避免整筆優惠被誤刪。"""
    t = normalize_space(line)
    t = re.sub(r"[（(]?\s*(?:圖|照片|圖片)\s*[／/]\s*(?:業者提供|資料圖|資料照|記者[^）)]*|[^）)]{0,24}提供)[）)]?", "", t)
    t = re.sub(r"[（(]?\s*圖片來源[^）)]*[）)]?", "", t)
    return normalize_space(t).strip(" ，、；;。")


def is_noise(line: str) -> bool:
    t = normalize_space(line)
    if re.match(r"^(圖|圖片|照片|翻攝|示意圖|資料照|廣告|延伸閱讀|相關新聞|更多新聞|加入為 Google|責任編輯|記者[：:])", t):
        return True
    cleaned = strip_caption(t)
    if len(cleaned) < 4:
        return True
    return False


def is_coffee_related(text: str) -> bool:
    t = str(text or "").lower()
    return any(k in t for k in ["咖啡", "cafe", "café", "美式", "拿鐵", "寄杯", "city cafe", "city tea", "city pearl", "let's tea", "let’s tea", "萊爾富", "星巴克", "路易莎", "美廉社", "showba"])


def find_store(text: str) -> str:
    t = normalize_space(text)
    # 品牌專屬系列名稱優先，避免「萊爾富文章裡提到7-ELEVEN」誤切換。
    if re.search(r"CITY\s*(?:CAFE|TEA|PEARL|PRIMA)|OPENPOINT", t, re.I) or re.search(r"7\s*[-－]?\s*(?:ELEVEN|11)", t, re.I):
        return "7-ELEVEN"
    if re.search(r"Let['’]?s\s*(?:Caf[eé]|Tea)|Fami!?ce|全家", t, re.I):
        return "全家"
    if re.search(r"萊爾富|Hi\s*[- ]?Life|Hi\s*Cafe", t, re.I):
        return "萊爾富"
    if re.search(r"OKmart|OK\s*超商|OKCAFE", t, re.I):
        return "OKmart"
    if re.search(r"美廉社", t):
        return "美廉社"
    if re.search(r"小北百貨|SHOWBA", t, re.I):
        return "小北百貨"
    if re.search(r"星巴克|Starbucks", t, re.I):
        return "星巴克"
    if re.search(r"路易莎|LOUISA", t, re.I):
        return "路易莎"
    if re.search(r"85\s*°?\s*C", t, re.I):
        return "85°C"
    if re.search(r"\bcama\b", t, re.I):
        return "cama"
    return ""


def is_caption_or_noise(line: str) -> bool:
    return is_noise(line) or bool(re.fullmatch(r"[（(].{0,30}[）)]", line))


def is_activity_context_line(line: str) -> bool:
    # date-bearing headings with promotion terms can establish context for following product bullets.
    return bool(DATE_RANGE_RE.search(line) or re.search(r"即日起.{0,20}(?:至|到|～|~)", line))


def extract_article_deals(article, fetched):
    if not fetched["ok"]:
        return []
    title = fetched.get("title") or article.get("title", "")
    url = fetched.get("final_url") or article.get("url", "")
    published = fetched.get("published") or article.get("published", "")
    lines = fetched.get("lines", [])
    out = []
    # 綜合懶人包標題可能同時提到多家店，不可以只因標題提到 7-ELEVEN 就誤標整篇優惠。
    title_store_matches = {name for name, pattern in STORE_PATTERNS if pattern.search(title or "")}
    title_store = find_store(title) if len(title_store_matches) == 1 else ""
    current_store = title_store
    context_start = context_end = ""
    context_date_text = ""
    previous_context_line = ""

    for line in lines:
        if is_caption_or_noise(line):
            continue
        # 品牌標題/活動標頭更新上下文，但導言同時列多家品牌時不更新。
        begins_store = find_store(line)
        if begins_store and (len(line) < 100 or line.startswith(("7-ELEVEN", "7－11", "全家", "萊爾富", "OKmart", "美廉社", "小北百貨", "CITY", "Let's", "Let’s", "Hi-Life", "SHOWBA"))):
            if current_store and begins_store != current_store:
                # 品牌區段變更時，清除上一家店的日期上下文，避免錯把上一區期限套給下一家。
                context_start = context_end = ""
                context_date_text = ""
            current_store = begins_store
        if is_activity_context_line(line):
            s, e, dt = date_context(line, published)
            if s or e:
                context_start = s.isoformat() if s else ""
                context_end = e.isoformat() if e else ""
                context_date_text = dt or line[:90]
                previous_context_line = line

        if not OFFER_RE.search(line) or not (8 <= len(line) <= 1000):
            continue
        # 對自身含日期的優惠行，優先用行內日期；否則才繼承明確的活動標頭日期。
        s, e, dt = date_context(line, published)
        if not (s or e) and context_date_text:
            s_text, e_text, dt_text = context_start, context_end, context_date_text
        else:
            s_text = s.isoformat() if s else ""
            e_text = e.isoformat() if e else ""
            dt_text = dt

        store = find_store(line) or current_store or title_store or "品牌待確認"
        # 不將全文導言含多家商店的句子整句記成優惠。
        if len(re.findall(r"7-ELEVEN|7-11|全家|萊爾富|OKmart|美廉社|小北百貨", line, re.I)) >= 3:
            continue
        out.append(make_deal(store, line, url, title, s_text, e_text, dt_text, published))
    return out


def normalize_key_text(value: str) -> str:
    # 正規化常見阿拉伯／中文數字與活動日期，讓跨媒體改寫同一優惠時更容易合併。
    value = normalize_space(value).lower().replace("let’s", "let's")
    value = re.sub(r"圖\s*[／/]\s*[^，。；]*", "", value)
    value = DATE_RANGE_RE.sub("", value)
    value = SINGLE_DATE_RE.sub("", value)
    for old, new in [("十", "10"), ("一", "1"), ("二", "2"), ("三", "3"), ("四", "4"), ("五", "5"), ("六", "6"), ("七", "7"), ("八", "8"), ("九", "9"), ("零", "0")]:
        value = value.replace(old, new)
    value = re.sub(r"同品項|限量|每會員限購|活動期間|優惠期間|原文註明|依原文|推出", "", value)
    value = re.sub(r"[\s　，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", value)
    # 店名/品牌系列已另作 key 欄位，從優惠文字移除其重複標示。
    for token in ["7-eleven", "7-11", "citycafe", "citycafé", "citytea", "citypearl", "cityprima", "openpoint", "全家", "萊爾富", "hi-life", "hilife"]:
        value = value.replace(token, "")
    return value


def deduplicate_deals(deals):
    """只在同品牌、正規化優惠及相同日期下合併；價格/杯數/日期不同仍保留。"""
    groups = {}
    for raw in deals:
        if not isinstance(raw, dict) or not raw.get("offer"):
            continue
        item = dict(raw)
        item["article_url"] = canonical_url(item.get("article_url", ""))
        urls = item.get("source_urls") or ([item["article_url"]] if item.get("article_url") else [])
        item["source_urls"] = list(dict.fromkeys(canonical_url(u) for u in urls if u))
        identity = normalize_key_text(item.get("offer", ""))
        # 短文字不跨來源合併，避免錯誤去重。
        key = (item.get("store", ""), identity, item.get("start_date", ""), item.get("end_date", ""))
        if len(identity) < 8:
            key = key + (item.get("article_url", ""),)
        if key not in groups:
            groups[key] = item
            continue
        old = groups[key]
        old["source_urls"] = list(dict.fromkeys((old.get("source_urls") or []) + item["source_urls"]))
        if not old.get("article_url") and item.get("article_url"):
            old["article_url"] = item["article_url"]
        # 若新條目提供更多日期資訊，只有在兩筆日期相容時才補入。
        for field in ("article_title", "published", "date_text"):
            if not old.get(field) and item.get(field):
                old[field] = item[field]
        old["needs_check"] = bool(old.get("needs_check", False) or item.get("needs_check", False))
        if item.get("category") == "coffee":
            old["category"] = "coffee"
    return list(groups.values())


def load_existing(path=OUTPUT_FILE):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("deals"), list):
            return data
        if isinstance(data, list):
            return {"deals": data}
        return None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def refresh_statuses(deals):
    for item in deals:
        item["status"] = infer_status(item.get("start_date", ""), item.get("end_date", ""))
        item.setdefault("needs_check", True)
        item.setdefault("category", "coffee")
    return deals


def safe_write(data, path=OUTPUT_FILE):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    articles = list(SEED_ARTICLES)
    rss_failures = 0
    for query in RSS_QUERIES:
        try:
            found = rss(query)
            logging.info("RSS OK (%s): %d articles", query, len(found))
            articles.extend(found)
        except Exception as exc:
            rss_failures += 1
            logging.warning("RSS ERROR (%s): %s", query, exc)

    unique_articles = {}
    for a in articles:
        url = canonical_url(a.get("url", ""))
        if not url:
            continue
        if url not in unique_articles:
            unique_articles[url] = {**a, "url": url}
        elif not unique_articles[url].get("published") and a.get("published"):
            unique_articles[url]["published"] = a["published"]

    to_fetch = list(unique_articles.values())[:MAX_ARTICLES]
    fetched_success = 0
    failed_urls = set()
    dynamic_deals = []
    for i, article in enumerate(to_fetch, 1):
        logging.info("[%d/%d] %s", i, len(to_fetch), article.get("title", article["url"]))
        result = fetch_article(article)
        if result["ok"]:
            fetched_success += 1
            dynamic_deals.extend(extract_article_deals(article, result))
        else:
            failed_urls.add(canonical_url(article.get("url", "")))
        time.sleep(REQUEST_DELAY_SECONDS)

    curated = curated_deals()
    fresh = deduplicate_deals(curated + dynamic_deals)
    previous = load_existing()

    # 若全部來源都被擋，將上一版與人工保底優惠合併，既不清空舊資料，也能寫入使用者已提供的新資訊。
    if fetched_success < MIN_SUCCESSFUL_ARTICLES_TO_REPLACE and previous and previous.get("deals"):
        logging.warning("本輪沒有文章成功讀取：採用既有資料 + 已知人工整理優惠，不用不完整結果覆寫成空清單。")
        fresh = deduplicate_deals(list(previous.get("deals", [])) + curated)

    # 只在某個原來源本輪讀取失敗時，暫時保留其中仍未到期的舊優惠；
    # 不把所有舊待確認/錯誤資料無限累加。
    if previous and isinstance(previous.get("deals"), list):
        preserve = []
        new_source_urls = {u for d in fresh for u in (d.get("source_urls") or [])}
        for old in previous["deals"]:
            if not isinstance(old, dict) or not old.get("offer"):
                continue
            urls = old.get("source_urls") or [old.get("article_url", "")]
            url_list = [canonical_url(u) for u in urls if u]
            if not url_list or not any(u in failed_urls for u in url_list):
                continue
            end_text = old.get("end_date") or ""
            try:
                if end_text and date.fromisoformat(end_text) < TODAY:
                    continue
            except ValueError:
                pass
            if old.get("start_date") or old.get("end_date") or old.get("status") == "verify":
                preserve.append(old)
        fresh = deduplicate_deals(fresh + preserve)

    final_deals = refresh_statuses(fresh)
    store_order = ["7-ELEVEN", "全家", "萊爾富", "OKmart", "美廉社", "小北百貨", "星巴克", "路易莎", "85°C", "cama", "全聯", "品牌待確認"]
    final_deals.sort(key=lambda d: (
        store_order.index(d.get("store")) if d.get("store") in store_order else len(store_order),
        d.get("start_date") or "9999-99-99",
        d.get("end_date") or "9999-99-99",
        d.get("offer", ""),
    ))

    counts = {s: sum(1 for d in final_deals if d.get("status") == s) for s in ["active", "upcoming", "verify", "expired"]}
    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "count": len(final_deals),
        "counts": counts,
        "disclaimer": (
            "資料來自固定指定新聞文章、使用者提供的已知優惠內容與 Google 新聞 RSS 搜尋。"
            "自動擷取可能因媒體防爬、網頁結構變動而漏抓；日期不完整者列為待確認。"
            "活動品項、限量、門市、會員條件與兌換規則請以來源原文及店家公告為準。"
        ),
        "deals": final_deals,
        "scrape_report": {
            "articles_discovered": len(to_fetch),
            "articles_fetched_successfully": fetched_success,
            "articles_failed_or_low_content": len(failed_urls),
            "rss_queries_failed": rss_failures,
            "curated_records": len(curated),
            "dynamic_records_before_dedup": len(dynamic_deals),
            "note": "若文章抓取成功數偏低，請在 GitHub Actions 日誌查看 FETCH ERROR；部分媒體可能封鎖自動存取。",
        },
    }
    safe_write(data)
    logging.info("Saved %d deals to %s", len(final_deals), OUTPUT_FILE)
    logging.info("Status counts: %s", counts)
    logging.info("Scrape report: %s", data["scrape_report"])


if __name__ == "__main__":
    main()
