#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
咖啡優惠候選擷取器：
- 搜尋 Applealmond、NOWnews 及其他公開新聞 RSS
- 嘗試抽取優惠行、日期、價格和原文連結
- 只有能從同一行/附近內容辨識明確起訖日期，且日期包含今天，才標為 active
- 日期不明的資料保留為 verify，不應冒充今日有效優惠
"""
import json, re, time, html
from datetime import datetime, date, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoffeeDealDigest/1.0)"}
MAX_ARTICLES = 30
QUERIES = [
    'site:applealmond.com/posts 咖啡優惠',
    'site:nownews.com 超商咖啡優惠',
    '咖啡優惠 7-ELEVEN 全家 萊爾富 美廉社 星巴克',
    '買一送一 咖啡 寄杯 優惠 台灣',
]
STORE_PATTERNS = [
    ("7-ELEVEN", r"7\s*[-－]?\s*ELEVEN|7-11|CITY\s*CAFE"),
    ("全家", r"全家|Let'?s\s*Café|Let'?s\s*Cafe"),
    ("萊爾富", r"萊爾富|Hi\s*Cafe|Hi-Life"),
    ("美廉社", r"美廉社"),
    ("OKmart", r"OKmart|OK\s*超商"),
    ("星巴克", r"星巴克|Starbucks"),
    ("路易莎", r"路易莎|LOUISA"),
    ("85°C", r"85\s*°?\s*C"),
    (" cama ", r"cama"),
]
OFFER_RE = re.compile(r"買\s*[一1]\s*送\s*[一1]|買\s*\d+\s*送\s*\d+|第\s*二\s*杯|第二杯|任選\s*\d+\s*杯|[兩二三四五六七八九十\d]+\s*杯\s*\d+\s*元|寄杯|折\s*扣|[特大中小]杯.{0,15}\d+\s*元|優惠價|組合價")
DATE_RE = re.compile(r"(?:(20\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?\s*(?:至|到|～|~|－|—|-|–)\s*(?:(20\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?")
SINGLE_DATE_RE = re.compile(r"(?:(20\d{2})\s*[年/.-]\s*)?(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日")

def rss(query):
    url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    res = requests.get(url, headers=HEADERS, timeout=25)
    res.raise_for_status()
    root = ET.fromstring(res.content)
    items = []
    for it in root.findall(".//item"):
        title = it.findtext("title") or ""
        link = it.findtext("link") or ""
        pub = it.findtext("pubDate") or ""
        if link:
            items.append({"title": html.unescape(title), "url": link, "published": pub})
    return items

def fetch(article):
    try:
        r = requests.get(article["url"], headers=HEADERS, timeout=25, allow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        lines = [re.sub(r"\s+", " ", x).strip(" •◾▪●　\t") for x in root.get_text("\n", strip=True).splitlines()]
        lines = [x for x in lines if x]
        title = soup.title.get_text(" ", strip=True) if soup.title else article["title"]
        return r.url, title, lines
    except Exception as exc:
        print("FETCH ERROR", article["url"], exc)
        return article["url"], article["title"], []

def make_date(y, m, d, fallback_year):
    y = int(y) if y else fallback_year
    try:
        return date(y, int(m), int(d))
    except ValueError:
        return None

def parse_range(s):
    m = DATE_RE.search(s)
    if not m:
        return None
    y1, m1, d1, y2, m2, d2 = m.groups()
    # If no year is given, use current year; handle year crossing.
    start = make_date(y1, m1, d1, TODAY.year)
    end = make_date(y2 or y1, m2, d2, TODAY.year)
    if start and end and not y2 and end < start and start.month >= 11 and end.month <= 2:
        end = date(start.year + 1, end.month, end.day)
    if start and end:
        return start, end, m.group(0)
    return None

def get_store(s):
    for name, pattern in STORE_PATTERNS:
        if re.search(pattern, s, re.I):
            return name.strip()
    return "綜合／待確認"

def extract(article, url, title, lines):
    out = []
    # Context windows help connect an activity date line with the following offer line.
    for i, line in enumerate(lines):
        if not OFFER_RE.search(line):
            continue
        if len(line) > 220 or len(line) < 5:
            continue
        context = " ".join(lines[max(0, i-2):min(len(lines), i+3)])
        parsed = parse_range(line) or parse_range(context)
        status = "verify"
        start_iso = end_iso = ""
        date_text = ""
        if parsed:
            start, end, date_text = parsed
            start_iso, end_iso = start.isoformat(), end.isoformat()
            status = "active" if start <= TODAY <= end else ("upcoming" if TODAY < start else "expired")
        # A date appearing in a headline alone is not enough to prove every offer is active.
        store = get_store(line + " " + " ".join(lines[max(0, i-3):i+1]))
        offer = line
        out.append({
            "store": store,
            "offer": offer,
            "status": status,
            "start_date": start_iso,
            "end_date": end_iso,
            "date_text": date_text,
            "article_title": title,
            "article_url": url,
            "published": article.get("published", ""),
            "source": "新聞文章自動擷取",
            "needs_check": True
        })
    return out

def main():
    found = []
    for q in QUERIES:
        try:
            found.extend(rss(q))
        except Exception as e:
            print("RSS ERROR", q, e)
    uniq = {}
    for a in found:
        uniq.setdefault(a["title"], a)
    articles = list(uniq.values())[:MAX_ARTICLES]
    deals = []
    for i, a in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {a['title']}")
        url, title, lines = fetch(a)
        if lines:
            deals.extend(extract(a, url, title, lines))
        time.sleep(1)
    dedup = {}
    for d in deals:
        dedup.setdefault((d["store"], d["offer"], d["article_url"]), d)
    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "disclaimer": "自動擷取可能漏抓、誤判或將文章中的其他日期套用到優惠。首頁只顯示明確日期判定為有效的項目；日期不明者請點原文確認。這不是官方即時庫存或價格保證。",
        "count": len(dedup),
        "deals": list(dedup.values())
    }
    with open("deals.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Saved", len(dedup), "candidate rows to deals.json")

if __name__ == "__main__":
    main()
