#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""省咖啡｜優惠雷達
- 修正精準品項與優惠特徵擷取，徹底解決跨新聞重複
- 修正店家專屬商品辨識，避免全家、萊爾富商品被誤認為 7-11
- 排除導言廢話、財經股市雜訊與誤植片段
"""

from __future__ import annotations

import html
import json
import os
import re
import time
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
URL_YAHOO_GENERAL = "https://tw.news.yahoo.com/4%E5%A4%A7%E8%B6%85%E5%95%86%E5%85%89%E5%BE%A9%E7%AF%80%E9%80%A3%E5%81%87-%E5%92%96%E5%95%A1%E8%B2%B71%E9%80%811-%E7%8F%8D%E5%A5%B610%E6%9D%AF360%E5%85%83-%E9%9C%9C%E6%B7%87%E6%B7%8B-%E6%9E%9C%E6%98%94%E5%8A%A0%E5%85%A5%E5%84%AA%E6%83%A0-014400310.html"
URL_YAHOO_TYPHOON = "https://tw.stock.yahoo.com/news/%E9%A2%B1%E9%A2%A8%E5%81%87%E5%92%96%E5%95%A1%E5%84%AA%E6%83%A0-%E8%90%8A%E7%88%BE%E5%AF%8C-%E8%B2%B7-%E9%80%81-7-043900203.html"
URL_NOWNEWS = "https://www.nownews.com/news/6884698"
URL_COSMO = "https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74211453/hilife-coffee-1022/"

SEED_ARTICLES = [
    {"title": "Yahoo 新聞｜四大超商光復節連假咖啡優惠", "url": URL_YAHOO_GENERAL, "published": "2026-10-22"},
    {"title": "中天新聞｜超商咖啡優惠整理", "url": URL_CTINEWS, "published": "2026-10-22"},
    {"title": "蘋果仁｜2026 光復節超商咖啡優惠懶人包", "url": URL_APPLE_329785, "published": "2026-10-22"},
    {"title": "Yahoo 新聞｜颱風假咖啡優惠、萊爾富買一送一", "url": URL_YAHOO_TYPHOON, "published": ""},
    {"title": "蘋果仁｜2026 本週咖啡優惠", "url": URL_APPLE_329295, "published": "2026-10-19"},
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
]

VALID_ITEMS = [
    "咖啡珍珠歐蕾", "珍珠奶茶", "珍珠撞奶", "香椰厚拿鐵", "厚濃抹茶拿鐵", "抹茶拿鐵", "燕麥拿鐵", 
    "重乳拿鐵", "濃萃美式", "濃萃拿鐵", "特濃美式", "特濃拿鐵", "單品美式", "單品拿鐵", "西西里", 
    "星沁爽", "冰淇淋紅茶", "檸檬青茶", "檸檬紅茶", "青梅冰茶", "蕎麥奶茶", "蕎麥茶", "水果茶", 
    "卡布奇諾", "瑪奇朵", "拿鐵", "美式", "抹茶", "珍珠", "紅茶", "綠茶", "青茶", "奶茶", "歐蕾", 
    "可可", "冰沙", "果昔", "霜淇淋", "咖啡"
]

DATE_RANGE_RE = re.compile(
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
    r"\s*(?:至|到|～|~|－|—|–|-|起至)\s*"
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
)
SINGLE_DATE_RE = re.compile(r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?")

def canonical_url(url: str) -> str:
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
    if not value: return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo: dt = dt.astimezone(TZ)
        return dt.date()
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo: dt = dt.astimezone(TZ)
        return dt.date()
    except Exception:
        return None

def date_context(text: str, published: str = ""):
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
            if end >= start:
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
    if e and e < TODAY: return "expired"
    if s and e:
        if s > TODAY: return "upcoming"
        if s <= TODAY <= e: return "active"
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

def find_store(text: str) -> str:
    """精準指紋辨識，避免不同商家的商品混淆"""
    t = normalize_space(text)
    
    # 1. 優先檢查精準品牌字眼
    if re.search(r"7\s*[-－]?\s*(?:ELEVEN|11)|統一超商", t, re.I): return "7-ELEVEN"
    if re.search(r"全家|FamilyMart", t, re.I): return "全家"
    if re.search(r"萊爾富|Hi\s*[- ]?Life", t, re.I): return "萊爾富"
    if re.search(r"OKmart|OK\s*超商", t, re.I): return "OKmart"
    if re.search(r"美廉社", t, re.I): return "美廉社"
    if re.search(r"小北百貨", t, re.I): return "小北百貨"
    if re.search(r"星巴克|Starbucks", t, re.I): return "星巴克"
    if re.search(r"路易莎|LOUISA", t, re.I): return "路易莎"
    if re.search(r"85\s*°?\s*C", t, re.I): return "85°C"
    if re.search(r"\bcama\b", t, re.I): return "cama"
    
    # 2. 若無品牌名，檢查各店專屬產品與活動特徵
    if re.search(r"CITY\s*(?:CAFE|TEA|PEARL|PRIMA)|OPENPOINT|濃萃|厚乳|不可思議|思樂冰|星級饗宴", t, re.I): return "7-ELEVEN"
    if re.search(r"Let['’]?s\s*(?:Caf[eé]|Tea)|Fami!?ce|單品(?:美式|拿鐵)|酷繽果|週三咖啡日|康康|好咖日|經典(?:美式|拿鐵)", t, re.I): return "全家"
    if re.search(r"Hi\s*Caf[eé]|重乳拿鐵", t, re.I): return "萊爾富"
    if re.search(r"OKCAFE|莊園級|極淬", t, re.I): return "OKmart"
    if re.search(r"SHOWBA", t, re.I): return "小北百貨"
    
    # 3. 處理「特濃」這個容易混淆的字
    if "特大特濃" in t: return "萊爾富" # 萊爾富專有名稱
    if "特濃" in t: return "全家" # 全家大杯特濃
    
    return ""

def is_junk_record(offer_text: str) -> bool:
    """過濾無關財經、導言、比較心得、無品項片段，並強制移除誤植資料"""
    t = normalize_space(offer_text)
    if len(t) < 4: return True
    
    # 移除網頁誤植的 3杯77元
    if "3杯77" in re.sub(r"\s+", "", t): return True

    # 阻擋財經與股市混入
    if any(k in t for k in ["股", "本益比", "增資", "營收", "大盤", "漲逾", "醫療保健", "公司債", "停班停課"]):
        return True
        
    # 阻擋新聞導言與心得雜訊
    if re.search(r"^(如果|反過來說|最後還是要提醒|連假當天|每天喝咖啡|不想一次|想買一送一|固定喝特選|和\s*7|想直|購買限制|提醒：)", t):
        return True
    if re.search(r"^(快來喝|颱風假|本周|4大超商|本週|超商咖啡寄杯|頂呱呱|▲.*日|▲.*活動檔期|其中)", t):
        return True
        
    # 必須包含具體品項，否則像「17杯500元」直接過濾
    if not any(item in t for item in VALID_ITEMS):
        return True

    # 必須有實際優惠機制
    has_mechanism = re.search(r"買\s*\d+\s*送\s*\d+|第\s*[二2]\s*杯|\d+\s*杯組?\s*\d+\s*元|\d+\s*折|均一價|單杯\s*\d+\s*元|加\s*10\s*元多|半價", t)
    if not has_mechanism:
        return True

    return False

def extract_deal_signature(deal: dict) -> tuple:
    """從優惠文字中擷取核心品項與優惠架構，做為跨新聞的統一去重指紋。"""
    offer = normalize_space(deal.get("offer", ""))
    store = deal.get("store") or "品牌待確認"
    
    # 去除干擾詞
    offer = re.sub(r"（[^）]*）|\([^)]*\)", "", offer) 
    for ch, n in [("十", "10"), ("一", "1"), ("二", "2"), ("三", "3"), ("四", "4"), ("五", "5"), ("六", "6"), ("七", "7"), ("八", "8"), ("九", "9")]:
        offer = offer.replace(ch, n)
        
    # 1. 抓出品項特徵
    matched_items = [i for i in VALID_ITEMS if i in offer]
    if any(x in matched_items for x in ["濃萃美式", "特濃美式", "單品美式", "經典美式"]) and "美式" in matched_items: 
        matched_items.remove("美式")
    if any(x in matched_items for x in ["濃萃拿鐵", "特濃拿鐵", "重乳拿鐵", "燕麥拿鐵", "單品拿鐵", "抹茶拿鐵", "香椰厚拿鐵", "厚濃抹茶拿鐵", "厚乳拿鐵", "經典拿鐵"]) and "拿鐵" in matched_items: 
        matched_items.remove("拿鐵")
    if any(x in matched_items for x in ["抹茶拿鐵", "厚濃抹茶拿鐵"]) and "抹茶" in matched_items: 
        matched_items.remove("抹茶")
    if len(matched_items) > 1 and "咖啡" in matched_items: 
        matched_items.remove("咖啡")
        
    product = "+".join(sorted(matched_items)) if matched_items else "未知品項"
    
    # 2. 抓出優惠機制特徵
    mech = ""
    m_buy = re.search(r"買\s*(\d+)\s*送\s*(\d+)", offer)
    if m_buy: mech = f"買{m_buy.group(1)}送{m_buy.group(2)}"
    
    if not mech:
        m_pack = re.search(r"(\d+)\s*杯組?\s*([\d,]+)\s*元", offer)
        if m_pack: mech = f"{m_pack.group(1)}杯{m_pack.group(2).replace(',', '')}