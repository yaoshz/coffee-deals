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
REQUEST_TIMEOUT = 12
MIN_SUCCESSFUL_ARTICLES_TO_REPLACE = 3

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
    r"|\d[\d,]*\s*杯\s*\d[\d,]*\s*元|\d+\s*(?:支|隻)\s*[\d,]+\s*元|\d+\s*件\s*[\d,]+\s*元|第\s*[二2]\s*件|寄杯|折\s*扣|打\s*\d+\s*折|\d+\s*折"
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


def sanitize_title(value: str) -> str:
    """移除已確認為誤植的 3 杯 77 元標題片段，保留其他有效新聞資訊。"""
    text = normalize_space(value)
    text = re.sub(r"7\s*[-－]?\s*(?:ELEVEN|11)\s*3\s*杯(?:組)?\s*77\s*元[，、,：:]?\s*", "", text, flags=re.I)
    text = re.sub(r"(?<!\d)3\s*杯(?:組)?\s*77\s*元[，、,：:]?\s*", "", text)
    return normalize_space(text)


# 明確排除已確認為誤植的「3 杯 77 元」優惠；此黑名單只針對該組杯數／總價，
# 不會誤刪「2 杯 77 元」等其他組合。
BLACKLISTED_PROMOTION_RE = re.compile(r"(?<!\d)3\s*杯(?:組)?\s*77\s*元", re.I)

def is_blacklisted_promotion(text: str) -> bool:
    return bool(BLACKLISTED_PROMOTION_RE.search(normalize_space(text)))


def normalize_offer(s: str) -> str:
    s = normalize_space(s).lower().replace("let’s", "let's")
    s = re.sub(r"圖\s*[／/]\s*[^，。；]*", "", s)
    s = re.sub(r"[\s ，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", s)
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
        "article_title": sanitize_title(title or "優惠文章"),
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

    ctit = "快來喝！超商咖啡寄杯買30送30 限今天加10元多1杯｜中天新聞網"
    add("品牌待確認", "大杯美式 7 杯組 255 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("品牌待確認", "大杯拿鐵 7 杯組 310 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("品牌待確認", "黑糖珍珠撞奶／珍珠奶茶 7 杯組 315 元", URL_CTINEWS, ctit, "2026-10-15", "2026-11-30", "10/15～11/30", "2026-10-22")
    add("全家", "Let's Tea 任選第二杯 8 折；商品依店舖實際供應為準，數量有限，售完為止。", URL_CTINEWS, ctit, "2026-10-22", "2026-11-10", "即日起～115/11/10（依原文）", "2026-10-22")

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
        line = normalize_space(part).strip(" •◾▪● \t\u200b")
        if len(line) < 3 or len(line) > 1200:
            continue
        if line not in lines:
            lines.append(line)
    return lines


def fetch_article(article):
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

        clean = []
        seen = set()
        for line in lines:
            line = strip_caption(normalize_space(line))
            key = re.sub(r"\W", "", line.lower())
            if not key or key in seen or is_noise(line):
                continue
            seen.add(key)
            clean.append(line)
        ok = len(clean) >= 2 and any(is_coffee_related(x) for x in [title, *clean])
        logging.info("FETCH %s (%s): %s lines", "OK" if ok else "LOW CONTENT", final_url, len(clean))
        if not ok:
            return {"ok": False, "url": url, "final_url": final_url, "title": title, "published": published, "lines": []}
        return {"ok": True, "url": url, "final_url": final_url, "title": title or article.get("title", ""), "published": published, "lines": clean}
    except Exception as exc:
        logging.warning("FETCH ERROR %s: %s", url, exc)
        return {"ok": False, "url": url, "final_url": url, "title": article.get("title", ""), "published": article.get("published", ""), "lines": []}


def strip_caption(line: str) -> str:
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


def classify_offer_category(offer: str) -> str:
    """將霜淇淋、果昔等相鄰促銷歸為 related，不混進核心咖啡優惠。"""
    text = normalize_space(offer)
    # 「除了咖啡之外」常只是背景句，不能因此把霜淇淋優惠錯標成咖啡。
    text = re.sub(r"(?:除了)?咖啡(?:優惠)?(?:之外|以外)(?:的部分)?", "", text)
    if re.search(r"霜淇淋|果昔|冰沙|冰品|甜點|零食", text) and not re.search(
        r"咖啡|美式|拿鐵|奶茶|紅茶|綠茶|青茶|抹茶|可可|歐蕾|瑪奇朵|寄杯|CITY\s*CAFE|CITY\s*TEA|Let's\s*Tea",
        text,
        re.I,
    ):
        return "related"
    return "coffee"


def is_caption_or_noise(line: str) -> bool:
    return is_noise(line) or bool(re.fullmatch(r"[（(].{0,30}[）)]", line))


def is_activity_context_line(line: str) -> bool:
    return bool(DATE_RANGE_RE.search(line) or re.search(r"即日起.{0,20}(?:至|到|～|~)", line))


def split_compound_offer(line: str):
    """若同一段真的列出多個獨立優惠，拆成單筆；單一優惠的補充說明不拆。"""
    parts = [normalize_space(p) for p in re.split(r"(?:[，、；;。]+|(?<!\d),(?!\d))", line or "") if normalize_space(p)]
    product_re = re.compile(
        r"咖啡|美式|拿鐵|拿堤|燕麥|重乳|特濃|濃萃|紅茶|綠茶|青茶|奶茶|抹茶|珍珠|"
        r"冰沙|果昔|霜淇淋|歐蕾|瑪奇朵|可可|蕎麥|檸檬茶|水果茶|星沁爽|厚乳|SHOWBA|星巴克|Starbucks|路易莎|Louisa|cama|丹堤|怡客|85\s*°?\s*C|茶品|茶|\btea\b",
        re.I,
    )
    valid = [p for p in parts if 8 <= len(p) <= 320 and OFFER_RE.search(p) and product_re.search(p)]
    # 至少兩個片段各自有品項與優惠機制，才判定為多筆優惠。
    if len(valid) >= 2:
        return valid
    return [normalize_space(line)]


def extract_article_deals(article, fetched):
    if not fetched["ok"]:
        return []
    title = fetched.get("title") or article.get("title", "")
    url = fetched.get("final_url") or article.get("url", "")
    published = fetched.get("published") or article.get("published", "")
    lines = fetched.get("lines", [])
    out = []
    title_store_matches = {name for name, pattern in STORE_PATTERNS if pattern.search(title or "")}
    title_store = find_store(title) if len(title_store_matches) == 1 else ""
    current_store = title_store
    context_start = context_end = ""
    context_date_text = ""
    previous_context_line = ""

    for line in lines:
        if is_caption_or_noise(line):
            continue
        begins_store = find_store(line)
        line_stores = {name for name, pattern in STORE_PATTERNS if pattern.search(line)}
        starts_with_store = line.startswith(("7-ELEVEN", "7－11", "7-11", "全家", "萊爾富", "OKmart", "美廉社", "小北百貨", "CITY", "Let's", "Let’s", "Hi-Life", "SHOWBA"))
        if len(line_stores) >= 2 and not starts_with_store:
            # 多品牌比較段不是單一店家的段落標題，清除上一個品牌上下文，避免下一筆優惠被錯標。
            current_store = ""
            context_start = context_end = ""
            context_date_text = ""
        elif begins_store and (len(line) < 100 or starts_with_store):
            if current_store and begins_store != current_store:
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

        for offer_line in split_compound_offer(line):
            if not OFFER_RE.search(offer_line) or not (8 <= len(offer_line) <= 1000):
                continue
            s, e, dt = date_context(offer_line, published)
            if not (s or e) and context_date_text:
                s_text, e_text, dt_text = context_start, context_end, context_date_text
            else:
                s_text = s.isoformat() if s else ""
                e_text = e.isoformat() if e else ""
                dt_text = dt

            store = find_store(offer_line) or current_store or title_store or "品牌待確認"
            # 要計算「不同品牌數」，不能把同一品牌在一句話出現多次當成多品牌導言。
            brand_hits = {name for name, pattern in STORE_PATTERNS if pattern.search(offer_line)}
            if len(brand_hits) >= 3:
                continue
            out.append(make_deal(store, offer_line, url, title, s_text, e_text, dt_text, published, category=classify_offer_category(offer_line)))
    return out


def is_non_offer_record(item):
    """濾除不完整的優惠片段、新聞導言、圖片說明與明顯無關的文章段落。"""
    text = normalize_space(item.get("offer", ""))
    if not text or is_noise(text):
        return True

    # 編輯性導言／心得不是一筆獨立優惠，避免同一優惠以長句重複出現。
    editorial_prefixes = (
        r"如果", r"不想一次", r"每天喝咖啡", r"固定喝", r"單看每杯價格",
        r"全家則從", r"萊爾富則", r"如果每天", r"如果只是", r"如果四杯",
        r"其中最便宜", r"這次另外", r"這波", r"不需要先", r"希望",
        r"超商咖啡寄杯買\s*30\s*送\s*30", r"大杯特濃拿鐵.*延伸閱讀",
    )
    if len(text) > 55 and any(re.search(r"^" + pattern, text, re.I) for pattern in editorial_prefixes):
        return True
    if "【延伸閱讀】" in text or "■ 活動時間" in text:
        # 僅有商品／促銷欄位與延伸閱讀混在一起的新聞殘句，不保留為卡片。
        if len(text) > 65 or "活動時間" in text:
            return True

    # 不含具體飲品名稱的「咖啡買30送30」通常是標題導言；具體美式／拿鐵項目另行保留。
    if re.search(r"咖啡.{0,12}買\s*30\s*送\s*30", text) and not re.search(r"美式|拿鐵|拿堤|特濃|濃萃|燕麥|重乳", text):
        return True

    if is_blacklisted_promotion(text):
        # 若同一句還含有別的有效優惠，交由 _split_multiple_promotions 拆出有效部分；
        # 但這張卡本身只描述「3 杯 77 元」時，必須直接排除。
        other_matches = [m for m in _primary_promotion_matches(text) if not is_blacklisted_promotion(m[2])]
        if not other_matches:
            return True
    if re.match(r"^[▲▼▶►◆◇☆★]", text):
        return True
    # 大量寄杯若只說「咖啡100杯」而沒有美式、拿鐵等實際品項，通常是新聞導言不是可核對優惠。
    bulk_match = re.search(r"(?<!\d)(\d{2,3})\s*杯", text)
    specific_drink = re.search(r"美式|拿鐵|拿堤|燕麥|重乳|特濃|濃萃|珍珠奶茶|珍珠撞奶|抹茶|紅茶|青茶|綠茶|可可|歐蕾", text)
    if bulk_match and int(bulk_match.group(1)) >= 50 and not specific_drink and "咖啡" in text:
        return True
    if re.match(r"^(?:4大超商|四大超商|超商咖啡優惠！|咖啡優惠懶人包|延伸閱讀|廣告|圖／|圖片來源)", text):
        return True
    if not OFFER_RE.search(text):
        return True

    # 僅有杯數和價格、沒有商品名稱的碎片，不應當成獨立優惠卡片。
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+杯(?:組)?[\d,]+元", compact):
        return True

    # 一張卡片若同時混有兩家以上店名，通常是新聞標題／跨店導言，不是一筆單店優惠。
    # 真正列出的各店優惠已在拆句階段分開；未拆開的混合句不再展示。
    brand_count = len({name for name, pattern in STORE_PATTERNS if pattern.search(text)})
    if brand_count >= 2:
        return True

    # 要有可辨識品項；單獨出現「茶」字容易讓一般新聞誤通過。
    valid_products = re.compile(
        r"咖啡|美式|拿鐵|拿堤|燕麥|重乳|特濃|濃萃|紅茶|綠茶|青茶|奶茶|抹茶|珍珠|"
        r"冰沙|果昔|霜淇淋|歐蕾|瑪奇朵|可可|蕎麥|檸檬茶|水果茶|星沁爽|厚乳|SHOWBA|星巴克|Starbucks|路易莎|Louisa|cama|丹堤|怡客|85\s*°?\s*C|茶品|茶|\btea\b",
        re.I,
    )
    if not valid_products.search(text):
        return True

    # 避免財經／股市文章因為偶然提及品牌與優惠詞而被當成優惠。
    financial = re.search(r"股價|股市|股票|盤中|收盤|台股|營收|每股盈餘|股利|法人買賣|投資人|漲停|跌停|財報", text, re.I)
    if financial and len(text) > 100 and not re.search(
        r"(?:美式|拿鐵|咖啡|飲品|茶|果昔|霜淇淋).{0,35}(?:買\s*[一1二2]?\s*送|第\s*[二2]杯|\d+\s*杯|\d[\d,]*\s*元|\d+\s*折|寄杯)",
        text,
        re.I,
    ):
        return True

    # 一段同時談多家品牌但沒有列出具體優惠的文章導言。
    brands = len({name for name, pattern in STORE_PATTERNS if pattern.search(text)})
    concrete_offers = len(re.findall(r"買\s*[一二三四五六七八九十\d]+\s*送\s*[一二三四五六七八九十\d]+|\d+\s*杯.{0,30}?[\d,]+\s*元|第\s*[二2]杯|\d+(?:\.\d+)?\s*折|寄杯", text, re.I))
    if brands >= 3 and concrete_offers < 2:
        return True

    # 超長散文通常是整段文章被誤抓，而不是單一優惠項目。
    if len(text) > 650 and concrete_offers < 2:
        return True
    return False


def _normalise_offer_core(value: str) -> str:
    """去除不影響優惠身份的品牌前綴、日期、平均單價與編輯備註。"""
    text = normalize_space(value).lower().replace("let’s", "let's")
    text = DATE_RANGE_RE.sub(" ", text)
    text = SINGLE_DATE_RE.sub(" ", text)

    # 先清掉括號內的原價／平均價等補充資訊，保留商品例外條件。
    text = re.sub(r"[（(][^）)]*(?:原價|平均(?:每杯)?|限量\s*[\d,]|每會員限購|依原文|原文註明|待確認|請查原文)[^）)]*[）)]", " ", text)
    text = re.sub(r"平均(?:每杯)?(?:約|不到)?\s*\d+(?:\.\d+)?\s*元?\s*(?:／\s*杯|/\s*杯|每杯)?", " ", text)
    text = re.sub(r"每杯(?:約|平均)?\s*\d+(?:\.\d+)?\s*元", " ", text)
    text = re.sub(r"原價\s*[\d,]+\s*元", " ", text)
    text = re.sub(r"限量\s*[\d,]*\s*(?:萬)?組|每會員限購\s*\d+\s*組", " ", text)
    text = re.sub(r"商品依店舖實際供應為準|數量有限|售完為止|原文註明|依文章標題|依原文|咖啡優惠(?:懶人包)?|優惠情報", " ", text)

    # 中文數字只轉換優惠規則會用到的數字，減少「一顆檸檬」等詞被變形的影響。
    for old, new in [("十", "10"), ("一", "1"), ("二", "2"), ("三", "3"), ("四", "4"), ("五", "5"), ("六", "6"), ("七", "7"), ("八", "8"), ("九", "9"), ("零", "0")]:
        text = text.replace(old, new)

    # 保留通用品類詞，否則 Let's Tea／CITY TEA 的無具體口味優惠會變成 unknown-product。
    text = re.sub(r"city\s*tea|let's\s*tea", " 茶品 ", text, flags=re.I)
    text = re.sub(r"city\s*caf[eé]|let's\s*caf[eé]", " 咖啡品項 ", text, flags=re.I)
    text = re.sub(
        r"7\s*[-－]?\s*(?:eleven|11)|city\s*pearl|city\s*prima|openpoint|"
        r"hi\s*[- ]?life|hi\s*caf[eé]|showba\s*caf[eé]",
        " ", text, flags=re.I,
    )
    # 「大杯」在有些報導中省略，有助合併同一活動；「特大杯」仍保留為不同杯型。
    text = text.replace("特大杯", "ZZSUPER_CUPZZ")
    text = text.replace("大杯", " ")
    text = text.replace("ZZSUPER_CUPZZ", "特大杯")
    text = text.replace("杯組", "杯")
    text = re.sub(r"[圖照片圖片]\s*[／/]\s*[^，。；]*", " ", text)
    return normalize_space(text)


def _product_signature(compact: str) -> str:
    """以較具體的飲品名稱為主；有明確品項時不再加上泛稱「咖啡／茶」。"""
    specific = [
        "咖啡珍珠歐蕾", "珍珠奶茶", "珍珠撞奶", "珍珠歐蕾", "香椰厚拿鐵", "厚濃抹茶拿鐵",
        "燕麥拿鐵", "重乳拿鐵", "濃萃美式", "特濃美式", "特濃拿鐵", "檸檬青茶", "檸檬紅茶",
        "青梅冰茶", "冰淇淋紅茶", "黃金蕎麥奶茶", "蕎麥奶茶", "水果茶", "果昔", "霜淇淋",
        "瑪奇朵", "拿鐵", "美式", "抹茶", "珍珠", "紅茶", "綠茶", "青茶", "奶茶", "歐蕾",
        "可可", "冰沙", "蕎麥茶", "星沁爽", "星巴克", "starbucks", "路易莎", "louisa", "cama", "丹堤", "怡客", "85°c",
    ]
    found = [token for token in specific if token in compact]
    if not found:
        if "咖啡" in compact:
            found.append("咖啡")
        elif re.search(r"(?<!蕎麥)(?<!水果)茶", compact):
            found.append("茶")
    else:
        # 商品已有具體品項名稱時，「咖啡」「茶」通常只是泛稱，不作為額外差異。
        found = [token for token in found if token not in {"咖啡", "茶"}]
    modifiers = [m for m in ["燕麥", "重乳", "特濃", "濃萃", "精品", "厚乳", "椰奶", "特大杯"] if m in compact]
    return "+".join(sorted(set(found + modifiers))) or "unknown-product"


def _promotion_signature(compact: str) -> str:
    """只取真正優惠條件，忽略原價、平均價、限量等不穩定數字。"""
    patterns = [
        ("buy-send", r"買\s*(\d+)\s*送\s*(\d+)"),
        ("second-cup", r"第\s*2\s*杯\s*(\d+)\s*(元|折)"),
        ("second-item", r"第\s*2\s*件\s*(\d+)\s*折"),
        ("cup-price", r"(\d+)\s*杯.{0,30}?([\d,]+)\s*元"),
        ("unit-price", r"(\d+)\s*(?:支|隻)\s*([\d,]+)\s*元"),
        ("item-price", r"(\d+)\s*件\s*([\d,]+)\s*元"),
        ("single-price", r"單杯\s*([\d,]+)\s*元"),
    ]
    matches = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, compact):
            vals = [re.sub(r",", "", x) for x in match.groups()]
            matches.append(label + ":" + ":".join(vals))
    if matches:
        return ";".join(sorted(set(matches)))
    # 沒有明確杯數／價格時，折數仍可代表優惠條件。
    discounts = sorted(set(re.findall(r"(?<!\d)(\d+(?:\.\d+)?)\s*折", compact)))
    if discounts:
        return "discount:" + ",".join(discounts)
    return "text:" + re.sub(r"[\s，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", compact)


def semantic_offer_key(item):
    """建立可比較的語意鍵；不把平均單價、原價或限量數字當成優惠本體。"""
    original = normalize_space(item.get("offer", ""))
    store = normalize_space(item.get("store", ""))
    if not store or store in {"品牌待確認", "店家待確認", "未知品牌"}:
        store = find_store(original) or store or "品牌待確認"
    core = _normalise_offer_core(original)
    compact = re.sub(r"[\s ，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", core)
    product = _product_signature(compact)
    promotion = _promotion_signature(core)
    feature = product + "|" + promotion
    start = item.get("start_date", "") or ""
    end = item.get("end_date", "") or ""
    period = f"{start}/{end}" if start and end else "unknown-period"
    return store, feature, period


def _dates_compatible(a, b):
    """有明確且互相矛盾的起訖日期就不合併；未知日期可被完整日期補齊。"""
    for field in ("start_date", "end_date"):
        av = (a.get(field) or "").strip()
        bv = (b.get(field) or "").strip()
        if av and bv and av != bv:
            return False
    return True


def _product_identity(value: str):
    """回傳飲品與規格；杯型取自原文，不能先被清理掉。"""
    original = normalize_space(value).lower()
    original = re.sub(r"特大(?!杯)", "特大杯", original)
    size = "特大杯" if re.search(r"特大杯", original) else ("大杯" if re.search(r"(?<!特)大杯", original) else ("中杯" if "中杯" in original else ""))
    text = _normalise_offer_core(original)
    text = re.sub(r"特大(?!杯)", "特大杯", text)
    text = re.sub(r"[\s，。、；：:！!？?（）()\[\]【】「」『』,.／/～~－—–_-]", "", text)
    terms = [
        "咖啡珍珠歐蕾", "厚濃抹茶拿鐵", "香椰厚拿鐵", "黃金蕎麥奶茶", "冰淇淋紅茶",
        "珍珠奶茶", "珍珠撞奶", "珍珠歐蕾", "燕麥拿鐵", "重乳拿鐵", "濃萃美式",
        "特濃美式", "特濃拿鐵", "檸檬青茶", "檸檬紅茶", "青梅冰茶", "蕎麥奶茶",
        "水果茶", "瑪奇朵", "霜淇淋", "蕎麥茶", "星沁爽", "美式", "拿鐵", "抹茶",
        "珍珠", "紅茶", "綠茶", "青茶", "奶茶", "歐蕾", "可可", "冰沙", "咖啡", "茶品", "茶"
    ]
    hits = []
    occupied = []
    for term in sorted(terms, key=len, reverse=True):
        pos = 0
        while True:
            idx = text.find(term, pos)
            if idx < 0:
                break
            end = idx + len(term)
            if not any(idx < b and end > a for a, b in occupied):
                hits.append(term)
                occupied.append((idx, end))
            pos = idx + 1
    products = frozenset(hits)
    if products - {"咖啡", "茶", "茶品"}:
        products = frozenset(p for p in products if p not in {"咖啡", "茶", "茶品"})
    modifiers = {m for m in ["特濃", "濃萃", "燕麥", "重乳", "精品", "厚乳", "椰奶", "特選", "厚濃"] if m in original}
    if size:
        modifiers.add("size:" + size)
    return products, frozenset(modifiers)


def _products_compatible(a: str, b: str) -> bool:
    pa, ma = _product_identity(a)
    pb, mb = _product_identity(b)
    if not (pa and pb and pa.intersection(pb)):
        return False
    # 特殊品項規格（特濃／濃萃／燕麥等）必須相同；杯型如有明示則不可互相矛盾。
    size_keys = {"size:特大杯", "size:大杯", "size:中杯"}
    sa, sb = ma & size_keys, mb & size_keys
    if sa and sb and sa != sb:
        return False
    return (ma - size_keys) == (mb - size_keys)


def _primary_promotion_matches(text: str):
    """找出文字裡的主要促銷條件；原價、折數與平均單價不視為額外優惠。"""
    pattern = re.compile(
        r"買\s*[一二三四五六七八九十\d]+\s*送\s*[一二三四五六七八九十\d]+"
        r"|第\s*[二2]\s*杯\s*[\d.]+\s*(?:元|折)"
        r"|第\s*[二2]\s*件\s*[\d.]+\s*折"
        r"|(?<!\d)\d+\s*杯(?:組)?[^，,、；;。\n]{0,22}?[\d,]+\s*元"
        r"|(?<!\d)\d+\s*(?:支|隻|件)\s*[^，,、；;。\n]{0,16}?[\d,]+\s*元",
        re.I,
    )
    matches = []
    for m in pattern.finditer(text):
        frag = m.group(0)
        if re.search(r"平均|每杯約|原價|特價|折數", frag):
            continue
        sig = re.sub(r"\s+|,", "", frag).lower()
        matches.append((m.start(), m.end(), frag, sig))
    # 同一條件重複提及不當作兩檔活動。
    return matches


def _split_multiple_promotions(text: str):
    """把「2 杯 66 元、3 杯 77 元」這種同段多優惠拆成獨立且較短的卡片。"""
    original = normalize_space(text)
    all_matches = _primary_promotion_matches(original)
    has_blocklisted = any(is_blacklisted_promotion(m[2]) for m in all_matches)
    matches = [m for m in all_matches if not is_blacklisted_promotion(m[2])]
    unique_sigs = {m[3] for m in matches}
    if not matches:
        return [] if has_blocklisted else [original]
    if len(unique_sigs) < 2 and not has_blocklisted:
        return [original]

    product_re = re.compile(
        r"咖啡|美式|拿鐵|拿堤|燕麥|重乳|特濃|濃萃|紅茶|綠茶|青茶|奶茶|抹茶|珍珠|"
        r"冰沙|果昔|霜淇淋|歐蕾|瑪奇朵|可可|蕎麥|檸檬茶|水果茶|星沁爽|厚乳|茶品|茶品|\btea\b",
        re.I,
    )
    out = []
    previous_context = ""
    previous_end = None
    previous_sep = ""
    for start, end, fragment, sig in matches:
        before = original[:start]
        # 依逗號／句號切出目前產品語境；「、」通常是同一列促銷的延續。
        last_sep = max(before.rfind(ch) for ch in "，,、；;。")
        context = normalize_space(before[last_sep + 1:])
        between = original[previous_end:start] if previous_end is not None else ""
        if not product_re.search(context):
            if previous_context and re.fullmatch(r"\s*、\s*", between):
                context = previous_context
            else:
                # 沒有明確品項的下一條價格（如「指定風味熱飲 7 杯 333 元」）不猜品項。
                continue
        elif previous_context and re.fullmatch(r"\s*、\s*", between):
            # 同一列的第二個品項若省略共同杯型，沿用前一項的「大杯／特大杯」。
            for size in ("特大杯", "大杯"):
                if size in previous_context and size not in context:
                    context = size + context
                    break
        # 去掉文章敘述語，保留品牌／杯型／飲品名稱。
        context = re.sub(r"^(?:其中|另外|此外|活動期間|期間|推出|還有|可享|則是)+\s*", "", context)
        context = re.sub(r"(?:可享|享有|推出|優惠價為|只要|則是|等於|活動期間)$", "", context).strip(" ：:，,")
        if not product_re.search(context):
            continue
        previous_context = context
        previous_end = end
        out.append(normalize_space(f"{context} {fragment}"))
    return out if out else [original]


def _clean_offer_display(text: str) -> str:
    """移除新聞導言開頭的品牌重覆與敘述動詞，卡片只顯示優惠本身。"""
    value = normalize_space(text)
    value = re.sub(r"^7\s*[-－]?\s*(?:eleven|11)\s*(?:推出有|推出|表示|指出|也推出|也有|有)\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:推出有|推出|優惠內容為|優惠為|優惠是)\s*", "", value)
    value = re.sub(r"^7\s*[-－]?\s*(?:eleven|11)\s*[：:]\s*", "", value, flags=re.I)
    value = re.sub(r"^7\s*[-－]?\s*(?:eleven|11)\s+光復節連假前率先開跑[^，,；;。]*[，,：:]\s*", "", value, flags=re.I)
    value = re.sub(r"^其中\s*", "", value)
    return normalize_space(value)


def _store_evidence_compatible(a, b) -> bool:
    """店家歸屬更正的寬鬆比對：僅用於大量寄杯價相同的強佐證。"""
    promo_a = _promotion_signature(_normalise_offer_core(a.get("offer", "")))
    promo_b = _promotion_signature(_normalise_offer_core(b.get("offer", "")))
    if promo_a != promo_b or not _date_records_compatible(a, b):
        return False
    qty_price = re.search(r"cup-price:(\d+):(\d+)", promo_a)
    if not qty_price or int(qty_price.group(1)) < 50:
        return False
    text_a, text_b = a.get("offer", ""), b.get("offer", "")
    base = ("美式", "拿鐵", "珍珠奶茶", "珍珠撞奶")
    return any(term in text_a and term in text_b for term in base)


def _bulk_records_compatible(a, b) -> bool:
    """大量寄杯價格相同時，容許一個來源省略「濃萃」等修飾詞。"""
    promo_a = _promotion_signature(_normalise_offer_core(a.get("offer", "")))
    promo_b = _promotion_signature(_normalise_offer_core(b.get("offer", "")))
    if promo_a != promo_b or not _date_records_compatible(a, b):
        return False
    m = re.fullmatch(r"cup-price:(\d+):(\d+)", promo_a)
    if not m or int(m.group(1)) < 50:
        return False
    ta, tb = normalize_space(a.get("offer", "")), normalize_space(b.get("offer", ""))
    shared_base = any(re.search(term, ta) and re.search(term, tb) for term in (r"美式", r"拿鐵", r"珍珠奶茶", r"珍珠撞奶"))
    if not shared_base:
        return False
    # 若兩邊明確寫不同杯型，不能因為總價相同就合併。
    _, ma = _product_identity(ta)
    _, mb = _product_identity(tb)
    sizes = {"size:特大杯", "size:大杯", "size:中杯"}
    sa, sb = ma & sizes, mb & sizes
    return not (sa and sb and sa != sb)


def _expand_offer_text(text: str):
    parts = split_compound_offer(text)
    out = []
    for part in parts:
        out.extend(_split_multiple_promotions(part))
    # 文字層去重，防止分割過程重覆建立同一個短句。
    return list(dict.fromkeys(p for p in out if p and not is_blacklisted_promotion(p)))


def _date_ranges_overlap(a, b) -> bool:
    try:
        a_start, a_end = date.fromisoformat(a.get("start_date", "")), date.fromisoformat(a.get("end_date", ""))
        b_start, b_end = date.fromisoformat(b.get("start_date", "")), date.fromisoformat(b.get("end_date", ""))
        return max(a_start, b_start) <= min(a_end, b_end)
    except (ValueError, TypeError):
        return False


def _date_records_compatible(a, b) -> bool:
    if _dates_compatible(a, b) or _date_ranges_overlap(a, b):
        return True
    # 一筆缺少開始日、但已知截止日接近另一筆完整活動期間時，允許去重並採用完整日期。
    try:
        a_start, a_end = a.get("start_date", ""), date.fromisoformat(a.get("end_date", ""))
        b_start, b_end = b.get("start_date", ""), date.fromisoformat(b.get("end_date", ""))
        if not a_start and b_start and abs((a_end - b_end).days) <= 7 and max(a_end, b_end) >= TODAY:
            return True
        if not b_start and a_start and abs((a_end - b_end).days) <= 7 and max(a_end, b_end) >= TODAY:
            return True
    except (ValueError, TypeError):
        pass
    return False


def _share_source(a, b) -> bool:
    au = set(canonical_url(u) for u in (a.get("source_urls") or [a.get("article_url", "")]) if u)
    bu = set(canonical_url(u) for u in (b.get("source_urls") or [b.get("article_url", "")]) if u)
    return bool(au.intersection(bu))


def _date_record_is_better(candidate, current) -> bool:
    """來源與活動期間衝突但重疊時，優先保留今天實際生效的期間；其次才取較新的起日。"""
    def interval(row):
        try:
            return date.fromisoformat(row.get("start_date", "")), date.fromisoformat(row.get("end_date", ""))
        except (ValueError, TypeError):
            return None
    ci, oi = interval(candidate), interval(current)
    if ci and not oi:
        return True
    if oi and not ci:
        return False
    if not ci or not oi:
        return bool(candidate.get("start_date") and candidate.get("end_date")) and not bool(current.get("start_date") and current.get("end_date"))
    c_active = ci[0] <= TODAY <= ci[1]
    o_active = oi[0] <= TODAY <= oi[1]
    if c_active != o_active:
        return c_active
    return ci[0] > oi[0]



def _offer_quality(offer: str) -> tuple:
    text = normalize_space(offer)
    products, modifiers = _product_identity(text)
    core = _normalise_offer_core(text)
    promo = _promotion_signature(core)
    structured = bool(re.search(r"買\s*[一二三四五六七八九十\d]+\s*送|第\s*[二2]\s*杯|\d+\s*杯.{0,25}?[\d,]+\s*元|單杯\s*\d+\s*元", core))
    # 優先展示短而完整的優惠句，避免整段新聞導言蓋過簡短的優惠項目。
    size_specificity = int(bool(re.search(r"特大杯|特大美式|特大拿鐵|(?<!特)大杯|中杯", text)))
    # 兩筆同促銷重疊時，優先保留品項明確、杯型明確且非整段新聞導言的描述。
    # 商品集合較少代表品項範圍較精確（例如「大杯美式」優於「大杯美式／拿鐵」）。
    return (int(structured), size_specificity, len(modifiers), -len(products), -len(text), -len(promo))


def deduplicate_deals(deals):
    """先拆多促銷，再依店家、商品、優惠條件與日期做去重；不再跨店合併未知品牌。"""
    groups = []
    expanded = []
    unknown_stores = {"", "品牌待確認", "店家待確認", "未知品牌"}

    for raw in deals:
        if not isinstance(raw, dict) or not raw.get("offer"):
            continue
        for offer_part in _expand_offer_text(str(raw.get("offer", ""))):
            if is_blacklisted_promotion(offer_part):
                continue
            item = dict(raw)
            item["article_title"] = sanitize_title(item.get("article_title", ""))
            explicit_store = find_store(offer_part)
            item["offer"] = _clean_offer_display(offer_part)
            title = normalize_space(item.get("article_title", ""))
            title_stores = {name for name, pattern in STORE_PATTERNS if pattern.search(title)}
            has_store_evidence = bool(explicit_store) or len(title_stores) == 1
            if explicit_store:
                item["store"] = explicit_store
            elif normalize_space(item.get("store", "")) in unknown_stores and len(title_stores) == 1:
                item["store"] = next(iter(title_stores))

            # 舊版曾將中天的「跨超商」文章裡未標明品牌的優惠，沿用上一段的 7-ELEVEN 標籤。
            # 這三筆是 curated_deals() 原本刻意標成品牌待確認的資料，這裡復原保守標籤。
            source_urls = item.get("source_urls") or []
            source_urls = [canonical_url(u) for u in source_urls if u]
            article_url = canonical_url(item.get("article_url", ""))
            is_cti_source = article_url == URL_CTINEWS or canonical_url(URL_CTINEWS) in source_urls
            if is_cti_source and not explicit_store and re.search(
                r"(?:大杯美式\s*7\s*杯(?:組)?\s*255\s*元|大杯拿鐵\s*7\s*杯(?:組)?\s*310\s*元|珍珠奶茶\s*7\s*杯(?:組)?\s*315\s*元|CAFE\s*RESERVE)",
                offer_part, re.I,
            ):
                item["store"] = "品牌待確認"
                has_store_evidence = False

            item["_store_explicit"] = has_store_evidence
            item["category"] = classify_offer_category(offer_part)
            expanded.append(item)

    # 店家歸屬只能用「優惠文字本身明確寫出的品牌」校正；
    # 不因相同價格、杯數或新聞標題提及某品牌，就把未知／混合文章的優惠猜成該品牌。
    for item in expanded:
        if find_store(item.get("offer", "")):
            continue
        candidate_stores = set()
        for other in expanded:
            if other is item:
                continue
            explicit_brand = find_store(other.get("offer", ""))
            if not explicit_brand:
                continue
            same_source = _share_source(item, other)
            if not same_source and not _bulk_records_compatible(item, other):
                continue
            if not _date_records_compatible(item, other):
                continue
            if _promotion_signature(_normalise_offer_core(item.get("offer", ""))) != _promotion_signature(_normalise_offer_core(other.get("offer", ""))):
                continue
            # 需存在同一個明確飲品類別；不靠「咖啡」這種泛詞交叉推斷。
            a_text, b_text = normalize_space(item.get("offer", "")), normalize_space(other.get("offer", ""))
            specific_terms = ("美式", "拿鐵", "珍珠奶茶", "珍珠撞奶", "抹茶拿鐵", "紅茶", "青茶", "水果茶")
            if not any(term in a_text and term in b_text for term in specific_terms):
                continue
            candidate_stores.add(explicit_brand)
        if len(candidate_stores) == 1:
            item["store"] = next(iter(candidate_stores))

    for item in expanded:
        if is_non_offer_record(item):
            continue
        item = dict(item)
        item.pop("_store_explicit", None)
        item["article_url"] = canonical_url(item.get("article_url", ""))
        urls = item.get("source_urls") or ([item["article_url"]] if item["article_url"] else [])
        if item.get("article_url"):
            urls = list(urls) + [item["article_url"]]
        item["source_urls"] = list(dict.fromkeys(canonical_url(u) for u in urls if u))
        store = normalize_space(item.get("store", "")) or "品牌待確認"
        item["store"] = store
        core = _normalise_offer_core(item["offer"])
        promo = _promotion_signature(core)

        candidates = []
        for old in groups:
            if normalize_space(old.get("store", "")) != store:
                continue
            if _promotion_signature(_normalise_offer_core(old.get("offer", ""))) != promo:
                continue
            if not (_products_compatible(old.get("offer", ""), item.get("offer", "")) or _bulk_records_compatible(old, item)):
                continue
            if not _date_records_compatible(old, item):
                continue
            candidates.append(old)

        if not candidates:
            groups.append(item)
            continue

        # 如果「美式／拿鐵」這種合併句同時符合多個單品版本，收斂成一張卡片。
        match = candidates[0]
        for duplicate_group in candidates[1:]:
            match["source_urls"] = list(dict.fromkeys((match.get("source_urls") or []) + (duplicate_group.get("source_urls") or [])))
            if _offer_quality(duplicate_group.get("offer", "")) > _offer_quality(match.get("offer", "")):
                match["offer"] = duplicate_group["offer"]
            if _date_record_is_better(duplicate_group, match):
                match["start_date"] = duplicate_group.get("start_date", match.get("start_date", ""))
                match["end_date"] = duplicate_group.get("end_date", match.get("end_date", ""))
                match["date_text"] = duplicate_group.get("date_text", match.get("date_text", ""))
            groups.remove(duplicate_group)

        match["source_urls"] = list(dict.fromkeys((match.get("source_urls") or []) + item["source_urls"]))
        if _date_records_compatible(match, item) and _date_record_is_better(item, match):
            match["start_date"] = item.get("start_date", match.get("start_date", ""))
            match["end_date"] = item.get("end_date", match.get("end_date", ""))
            match["date_text"] = item.get("date_text", match.get("date_text", ""))
        old_offer = match.get("offer", "")
        if _offer_quality(item.get("offer", "")) > _offer_quality(old_offer):
            match["offer"] = item["offer"]
            for field in ("article_url", "article_title", "published"):
                if item.get(field):
                    match[field] = item[field]
        for field in ("article_title", "published"):
            if not match.get(field) and item.get(field):
                match[field] = item[field]
        if match.get("date_text") in {None, "", "活動日期尚待確認", "日期未明"} and item.get("date_text"):
            match["date_text"] = item["date_text"]
        match["needs_check"] = bool(match.get("needs_check", False) or item.get("needs_check", False))
        if classify_offer_category(match.get("offer", "")) == "related":
            match["category"] = "related"
        else:
            match["category"] = "coffee"

    return groups


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
    empty_extraction_urls = set()
    dynamic_deals = []
    for i, article in enumerate(to_fetch, 1):
        logging.info("[%d/%d] %s", i, len(to_fetch), article.get("title", article["url"]))
        result = fetch_article(article)
        if result["ok"]:
            fetched_success += 1
            extracted = extract_article_deals(article, result)
            dynamic_deals.extend(extracted)
            # 頁面讀取成功但沒有解析出優惠時，也保留該來源尚未過期的舊記錄。
            # 這可降低網站改版／抽取規則短暫失效造成資料突然消失的風險。
            if not extracted:
                empty_extraction_urls.add(canonical_url(article.get("url", "")))
                empty_extraction_urls.add(canonical_url(result.get("final_url", "")))
        else:
            failed_urls.add(canonical_url(article.get("url", "")))
        time.sleep(REQUEST_DELAY_SECONDS)

    curated = curated_deals()
    fresh = deduplicate_deals(curated + dynamic_deals)
    previous = load_existing()

    if fetched_success < MIN_SUCCESSFUL_ARTICLES_TO_REPLACE and previous and previous.get("deals"):
        logging.warning("本輪成功讀取文章數偏低：採用既有資料 + 已知人工整理優惠，避免用不完整結果覆寫舊資料。")
        fresh = deduplicate_deals(list(previous.get("deals", [])) + curated)

    if previous and isinstance(previous.get("deals"), list):
        preserve = []
        for old in previous["deals"]:
            if not isinstance(old, dict) or not old.get("offer"):
                continue
            urls = old.get("source_urls") or [old.get("article_url", "")]
            url_list = [canonical_url(u) for u in urls if u]
            retainable_urls = failed_urls | empty_extraction_urls
            if not url_list or not any(u in retainable_urls for u in url_list):
                continue
            end_text = old.get("end_date") or ""
            try:
                if end_text and date.fromisoformat(end_text) < TODAY:
                    continue
            except ValueError:
                pass
            
            # 此處呼叫加強過的 is_non_offer_record，過濾掉已存在 json 裡但其實不合理的舊資料
            if is_non_offer_record(old):
                continue
                
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
            "urls_for_articles_with_no_extracted_offers": len(empty_extraction_urls),
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