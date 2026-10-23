#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
省咖啡｜優惠雷達 scraper.py

功能：
- 從 Google News RSS 搜尋咖啡優惠文章
- 解析文章中的多筆優惠
- 以段落標題及優惠文字判斷品牌
- 將日期不完整的優惠標示為 verify
- 跨文章合併重複優惠，對衝突日期採待確認而非猜測
- 輸出 GitHub Pages 使用的 deals.json

注意：
- 自動擷取無法保證涵蓋所有店家或所有優惠，請人工核對。
- 每次成功擷取後以本次結果重建資料，避免錯誤舊資料永久累積。若完全未抓到優惠則停止，不覆寫原檔。
"""

import json
import re
import time
import html
import os
from datetime import datetime, date, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
}

# RSS 結果常有重複，放寬上限以免少數媒體佔滿名額。
MAX_ARTICLES = 160
REQUEST_DELAY_SECONDS = 0.35

SEED_ARTICLES = [
    # 使用者明確指定的文章：直接抓取，不依賴 Google News RSS 是否回傳。
    {
        "title": "Cosmopolitan Taiwan｜萊爾富咖啡優惠",
        "url": "https://www.cosmopolitan.com/tw/lifestyle/hot-topics/g74211453/hilife-coffee-1022/",
        "published": "",
    },
    {
        "title": "Yahoo 新聞｜四大超商光復節連假咖啡優惠",
        "url": "https://tw.news.yahoo.com/4%E5%A4%A7%E8%B6%85%E5%95%86%E5%85%89%E5%BE%A9%E7%AF%80%E9%80%A3%E5%81%87-%E5%92%96%E5%95%A1%E8%B2%B71%E9%80%811-%E7%8F%8D%E5%A5%B610%E6%9D%AF360%E5%85%83-%E9%9C%9C%E6%B7%87%E6%B7%8B-%E6%9E%9C%E6%98%94%E5%8A%A0%E5%85%A5%E5%84%AA%E6%83%A0-014400310.html",
        "published": "",
    },
    {
        "title": "中天新聞｜超商咖啡優惠整理",
        "url": "https://ctinews.com/news/items/bKxrXQKYW9",
        "published": "",
    },
    {
        "title": "NOWnews｜本周咖啡優惠 10/19～10/25",
        "url": "https://www.nownews.com/news/6884698",
        "published": "",
    },
    {
        "title": "蘋果仁｜2026 本週咖啡優惠 10/19～10/25",
        "url": "https://applealmond.com/posts/329295",
        "published": "",
    },
    {
        "title": "蘋果仁｜2026 雙十國慶咖啡優惠懶人包",
        "url": "https://applealmond.com/posts/328076",
        "published": "",
    },
]

# 以指定文章 + 多媒體網站 RSS 搜尋並行；RSS 只是發現新文章的補充，不是唯一入口。
QUERIES = [
    '超商咖啡優惠 2026 10月 11月 買一送一',
    '7-ELEVEN CITY CAFE 咖啡優惠 寄杯 2026 10月',
    '全家 Let’s Café 咖啡優惠 寄杯 2026 10月',
    '全家 Let’s Tea 第二杯8折 11/10',
    '萊爾富 Hi Café 買一送一 2026 10月 11月',
    'OKmart OKCAFE 咖啡優惠 2026 10月',
    '美廉社 咖啡優惠 2026 10月 11月',
    '星巴克 台灣 咖啡優惠 2026 10月 11月',
    'site:cosmopolitan.com/tw/lifestyle/hot-topics/ 萊爾富 咖啡優惠',
    'site:applealmond.com/posts 本週咖啡優惠 2026',
    'site:nownews.com 超商咖啡優惠 2026 10月',
    'site:ctinews.com/news 超商咖啡優惠 2026 10月',
    'site:tw.news.yahoo.com 超商咖啡優惠 2026 10月',
    'site:nownews.com 萊爾富 買一送一 咖啡',
    'site:ctinews.com 萊爾富 咖啡 買一送一',
    'site:tw.news.yahoo.com 萊爾富 咖啡 買一送一',
]

# 品牌名稱及產品系列。較具體的名稱放前面，避免 CITY CAFE 被判成其他店。
STORE_PATTERNS = [
    ("7-ELEVEN", r"7\s*[-－]?\s*ELEVEN|7\s*[-－]?\s*11|CITY\s*CAFE"),
    ("全家", r"全家|Let['’]?s\s*Caf[eé]|Let['’]?s\s*Tea"),
    ("萊爾富", r"萊爾富|Hi\s*Cafe|Hi-Life"),
    ("OKmart", r"OKmart|OK\s*超商|OKCAFE"),
    ("美廉社", r"美廉社"),
    ("星巴克", r"星巴克|Starbucks"),
    ("路易莎", r"路易莎|LOUISA"),
    ("85°C", r"85\s*°?\s*C"),
    ("cama", r"\bcama\b"),
    ("全聯", r"全聯|大全聯"),
]

# 必須是優惠/價格/促銷文字才納入候選，避免把一般介紹當成優惠。
OFFER_RE = re.compile(
    r"買\s*[一1]\s*送\s*[一1]"
    r"|買\s*\d+\s*送\s*\d+"
    r"|第\s*二\s*杯|第二杯"
    r"|任選\s*\d+\s*杯"
    r"|[兩二三四五六七八九十\d]+\s*杯.{0,12}\d+\s*元"
    r"|\d+\s*杯\s*\d+\s*元"
    r"|寄杯|折\s*扣|打\s*\d+\s*折"
    r"|優惠價|組合價|現折|折價"
    r"|咖啡.{0,20}\d+\s*元"
    r"|大杯.{0,20}\d+\s*元"
    r"|加\s*\d+\s*元.{0,12}(多|再送)"
    r"|免費|送\s*[一1]\s*杯"
    r"|咖啡日",
    re.I,
)

DATE_RE = re.compile(
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
    r"\s*(?:至|到|～|~|－|—|-|–|起至)\s*"
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
)
SINGLE_DATE_RE = re.compile(
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
)


def rss(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    results = []
    for item in root.findall(".//item"):
        title = html.unescape(item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate") or ""
        if link:
            results.append({"title": title, "url": link, "published": published})
    return results


def fetch(article):
    """抓取文章正文；若媒體阻擋或文章無法讀取，回傳空行而非中斷整批工作。"""
    try:
        response = requests.get(
            article["url"], headers=HEADERS, timeout=30, allow_redirects=True
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]
        ):
            tag.decompose()

        root = (
            soup.find(attrs={"itemprop": "articleBody"})
            or soup.find("article")
            or soup.find("main")
            or soup.body
            or soup
        )

        lines = []
        for raw in root.get_text("\n", strip=True).splitlines():
            line = re.sub(r"\s+", " ", raw).strip(" •◾▪●　\t")
            if line and len(line) <= 900:
                lines.append(line)

        title = article.get("title", "")
        if soup.title:
            title = soup.title.get_text(" ", strip=True)

        print("FETCH OK:", response.url, "lines:", len(lines))
        return response.url, title, lines
    except Exception as exc:
        print("FETCH ERROR:", article.get("url", ""), str(exc))
        return article.get("url", ""), article.get("title", ""), []


def make_date(year, month, day, fallback_year):
    try:
        if year:
            y = int(year)
            if 1 <= y <= 191:
                y += 1911
        else:
            y = fallback_year
        return date(y, int(month), int(day))
    except (ValueError, TypeError):
        return None


def parse_range(text):
    """回傳 (start, end, date_text)。不確定起日的活動不猜測起日。"""
    if "即日起" in text:
        match = SINGLE_DATE_RE.search(text)
        if match:
            year, month, day = match.groups()
            end = make_date(year, month, day, TODAY.year)
            if end:
                return TODAY, end, match.group(0)

    match = DATE_RE.search(text)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()
        start = make_date(y1, m1, d1, TODAY.year)
        end = make_date(y2 or y1, m2, d2, TODAY.year)
        if start and end:
            # 跨年區間，例如 12/20～1/10。
            if not y1 and not y2 and end < start and start.month >= 10 and end.month <= 3:
                end = date(start.year + 1, end.month, end.day)
            if end >= start:
                return start, end, match.group(0)

    # 只有截止日：不要假設活動從今天開始。
    cutoff = re.search(
        r"(?:至|到|截止(?:日期)?(?:為|：|:)?|限定至|活動至)\s*"
        r"((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)",
        text,
    )
    if not cutoff:
        cutoff = re.search(
            r"((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)\s*前限定",
            text,
        )
    if cutoff:
        single = SINGLE_DATE_RE.search(cutoff.group(1))
        if single:
            year, month, day = single.groups()
            end = make_date(year, month, day, TODAY.year)
            if end:
                return None, end, single.group(0)

    return None


def get_store(text):
    """若優惠文字同時提及多個品牌，不在此處強行選擇。"""
    matches = []
    for name, pattern in STORE_PATTERNS:
        if re.search(pattern, text, re.I):
            if name not in matches:
                matches.append(name)
    return matches[0] if len(matches) == 1 else ""


def is_coffee_related(text):
    t = text.lower()
    keywords = (
        "咖啡", "cafe", "café", "星巴克", "路易莎", "萊爾富",
        "美廉社", "cama", "寄杯", "city cafe", "okcafe",
        "let's café", "let’s café", "let's tea", "let’s tea",
    )
    return any(word in t for word in keywords)


def heading_store_for_line(line):
    """只有整行像段落標題時才更新品牌，避免正文提到其他品牌就切換。"""
    cleaned = re.sub(r"[（(].*?[）)]", "", line).strip(" ：:　|｜")
    aliases = [
        ("7-ELEVEN", r"^(?:7\s*[-－]?\s*ELEVEN|7\s*[-－]?\s*11|CITY\s*CAFE)$"),
        ("全家", r"^(?:全家|Let['’]s\s*Caf[eé]|Let['’]s\s*Tea)$"),
        ("萊爾富", r"^(?:萊爾富|Hi\s*Cafe|Hi-Life)$"),
        ("OKmart", r"^(?:OKmart|OKCAFE)$"),
        ("美廉社", r"^美廉社$"),
        ("星巴克", r"^(?:星巴克|Starbucks)$"),
        ("路易莎", r"^(?:路易莎|LOUISA)$"),
        ("85°C", r"^85\s*°?\s*C$"),
        ("cama", r"^cama$"),
    ]
    for store, pattern in aliases:
        if re.match(pattern, cleaned, re.I):
            return store
    return ""


def split_mixed_store_line(line):
    """針對常見的同句多店寫法做安全拆分；其餘交給一般分類。"""
    patterns = [
        ("全家", r"全家推出"),
        ("萊爾富", r"萊爾富(?:則|推出|也)"),
        ("7-ELEVEN", r"(?:7-ELEVEN|7-11|7－11)(?:則|推出|也)"),
        ("OKmart", r"OKmart(?:則|推出|也)"),
        ("美廉社", r"美廉社(?:則|推出|也)"),
        ("星巴克", r"(?:星巴克|Starbucks)(?:則|推出|也)"),
    ]
    hits = []
    for store, pattern in patterns:
        m = re.search(pattern, line, re.I)
        if m:
            hits.append((m.start(), store, m.end()))
    hits.sort()
    if len(hits) < 2:
        return [(get_store(line), line)]

    pieces = []
    for i, (_, store, end) in enumerate(hits):
        next_start = hits[i + 1][0] if i + 1 < len(hits) else len(line)
        piece = line[end:next_start].strip(" ，,、；;。 ")
        if piece:
            pieces.append((store, piece))
    return pieces or [(get_store(line), line)]


def infer_status(start, end):
    if start and end:
        if end < TODAY:
            return "expired"
        if start > TODAY:
            return "upcoming"
        return "active"
    return "verify"


def is_caption_or_noise(line):
    """排除圖片說明、新聞導覽與純標籤，避免當成優惠。"""
    t = line.strip()
    noise_patterns = [
        r"^(?:圖|圖片|照片|翻攝|示意圖|資料照|圖／|圖/|照片／|照片/)",
        r"(?:業者提供|資料照|示意圖|圖片來源|新聞來源|圖／記者|圖/記者)",
        r"^(?:延伸閱讀|更多新聞|看更多|責任編輯|記者[：:])",
    ]
    return any(re.search(p, t, re.I) for p in noise_patterns)


def is_standalone_date_line(line):
    """只有幾乎純日期/活動期間的短行才可作為優惠行的日期補充。"""
    t = line.strip()
    if len(t) > 100 or OFFER_RE.search(t):
        return False
    has_date = bool(DATE_RE.search(t) or SINGLE_DATE_RE.search(t))
    if not has_date:
        return False
    return bool(re.fullmatch(
        r"[\s\d年月日號./～~至到－—–-起迄止限定即日起活動期間優惠期間：:()（）約至前後]*",
        t
    ))


def extract(article, url, title, lines):
    results = []
    if not is_coffee_related(title + " " + " ".join(lines)):
        print("SKIP unrelated article:", title)
        return results

    current_store = ""
    for idx, original_line in enumerate(lines):
        line = original_line.strip()
        if not line or is_caption_or_noise(line):
            continue

        heading = heading_store_for_line(line)
        if heading:
            current_store = heading
            continue

        if not OFFER_RE.search(line) or not 5 <= len(line) <= 500:
            continue

        # 不再把前後兩行的任意日期拼在一起。只接受相鄰的「純日期行」，
        # 若相鄰行本身是另一項優惠，絕不拿它的日期來判斷本項優惠。
        date_parts = [line]
        for j in (idx - 1, idx + 1):
            if 0 <= j < len(lines):
                candidate = lines[j].strip()
                if candidate and not is_caption_or_noise(candidate) and is_standalone_date_line(candidate):
                    date_parts.append(candidate)
        date_context = " ".join(date_parts)

        candidates = split_mixed_store_line(line)
        for line_store, offer_line in candidates:
            offer_line = offer_line.strip()
            if not offer_line or is_caption_or_noise(offer_line):
                continue
            store = line_store or get_store(offer_line) or current_store or get_store(title)
            if not store:
                store = "綜合／待確認"

            parsed = parse_range(date_context)
            start = parsed[0] if parsed else None
            end = parsed[1] if parsed else None
            date_text = parsed[2] if parsed else ""
            results.append({
                "store": store,
                "offer": offer_line,
                "status": infer_status(start, end),
                "start_date": start.isoformat() if start else "",
                "end_date": end.isoformat() if end else "",
                "date_text": date_text,
                "article_title": title,
                "article_url": url,
                "source_urls": [url] if url else [],
                "published": article.get("published", ""),
                "source": "新聞文章自動擷取",
                "needs_check": True,
            })
    return results


def normalize_offer(offer):
    """移除空白與常見標點，但保留價格、杯數、品項與折扣。"""
    value = str(offer or "").lower()
    value = value.replace("let’s", "let's")
    value = re.sub(r"[\s　，。；：、！!？?（）()\[\]【】「」『』,.]", "", value)
    return value


def offer_identity(offer):
    """優惠比對用文字：移除日期與新聞圖片註記，但保留價格、杯數、折扣。"""
    value = str(offer or "").lower()
    value = re.sub(r"(?:20\d{2}\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?", "", value)
    value = re.sub(r"圖\s*[／/]\s*業者提供|（?圖／[^）]*）?", "", value)
    return normalize_offer(value)


def deduplicate_deals(deals):
    """合併同店、相同優惠文字的跨媒體重複；日期衝突時不猜，改列待確認。"""
    unique = {}
    for raw in deals:
        if not isinstance(raw, dict) or not raw.get("offer"):
            continue
        item = dict(raw)
        store = str(item.get("store", "綜合／待確認")).strip()
        identity = offer_identity(item.get("offer", ""))
        # 文字過短時不做跨文章合併，避免將不同優惠誤合併。
        key = (store, identity) if len(identity) >= 12 else (
            store, identity, item.get("start_date", ""), item.get("end_date", ""), item.get("article_url", "")
        )
        item_urls = item.get("source_urls") or ([item.get("article_url")] if item.get("article_url") else [])
        item["source_urls"] = list(dict.fromkeys(u for u in item_urls if u))
        if key not in unique:
            unique[key] = item
            continue

        old = unique[key]
        old_urls = old.get("source_urls") or ([old.get("article_url")] if old.get("article_url") else [])
        old["source_urls"] = list(dict.fromkeys(old_urls + item["source_urls"]))
        # 日期相同或其中一筆沒有日期時，保留較完整的日期。
        old_range = (old.get("start_date", ""), old.get("end_date", ""))
        new_range = (item.get("start_date", ""), item.get("end_date", ""))
        old_complete = all(old_range)
        new_complete = all(new_range)
        if old_complete and new_complete and old_range != new_range:
            # 相同優惠文字卻出現互相衝突的日期，可能是日期誤配或重複刊登。
            # 不武斷選一個日期，將日期清空並交由前端顯示待確認。
            old["start_date"] = ""
            old["end_date"] = ""
            old["date_text"] = "日期來源衝突，請查原文"
            old["status"] = "verify"
            old["needs_check"] = True
        elif not old_complete and new_complete:
            old["start_date"], old["end_date"] = new_range
            old["date_text"] = item.get("date_text", "")
            old["status"] = item.get("status", "verify")
        for field in ("article_title", "article_url", "published"):
            if not old.get(field) and item.get(field):
                old[field] = item[field]
        old["needs_check"] = bool(old.get("needs_check", False) or item.get("needs_check", False))
    return list(unique.values())


def load_existing_deals(path="deals.json"):
    """讀取既有 deals.json；讀取失敗時不會覆寫原檔。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("deals"), list):
            return data["deals"]
        if isinstance(data, list):
            return data
        print("WARNING: deals.json 格式不熟悉，停止覆寫以避免遺失舊資料。")
        raise ValueError("Unsupported deals.json structure")
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        print("ERROR: deals.json JSON 格式錯誤，停止覆寫：", exc)
        raise


def deal_key(deal):
    """同店、同優惠、同日期才去重；日期不同的促銷一定保留。"""
    return (
        str(deal.get("store", "")).strip(),
        normalize_offer(deal.get("offer", "")),
        str(deal.get("start_date", "") or ""),
        str(deal.get("end_date", "") or ""),
    )


def merge_existing_and_new(existing, fresh):
    """合併新舊優惠；搜尋漏抓時不會讓舊資料整批消失。"""
    merged = {}
    for deal in existing + fresh:
        if not isinstance(deal, dict) or not deal.get("offer"):
            continue
        item = dict(deal)
        item.setdefault("store", "綜合／待確認")
        item.setdefault("status", "verify")
        item.setdefault("start_date", "")
        item.setdefault("end_date", "")
        key = deal_key(item)
        if key not in merged:
            merged[key] = item
            continue
        old = merged[key]
        # 保留較完整來源資訊，避免只因 RSS 結果缺欄位就丟掉舊內容。
        for field in ("date_text", "article_title", "article_url", "published", "source"):
            if not old.get(field) and item.get(field):
                old[field] = item[field]
        if old.get("status") == "verify" and item.get("status") in ("active", "upcoming", "expired"):
            old["status"] = item["status"]
        old["needs_check"] = bool(old.get("needs_check", False) or item.get("needs_check", False))
    return list(merged.values())


def refresh_statuses(deals):
    """依完整日期區間更新狀態；只有截止日或無日期的資料保留待確認。"""
    for deal in deals:
        try:
            start_text = deal.get("start_date") or ""
            end_text = deal.get("end_date") or ""
            start = date.fromisoformat(start_text) if start_text else None
            end = date.fromisoformat(end_text) if end_text else None
        except (TypeError, ValueError):
            continue
        if start and end:
            if end < TODAY:
                deal["status"] = "expired"
            elif start > TODAY:
                deal["status"] = "upcoming"
            else:
                deal["status"] = "active"
        else:
            # 不擅自把只有截止日的資料標成 active；但不刪除資料。
            deal["status"] = "verify"
    return deals

def main():
    found = list(SEED_ARTICLES)

    for query in QUERIES:
        try:
            items = rss(query)
            print("RSS OK:", query, "items:", len(items))
            found.extend(items)
        except Exception as exc:
            print("RSS ERROR:", query, str(exc))

    # 文章網址去重，保留不同媒體或不同文章。
    unique_articles = {}
    for article in found:
        url = article.get("url", "").strip()
        if url and url not in unique_articles:
            unique_articles[url] = article

    articles = list(unique_articles.values())[:MAX_ARTICLES]
    deals = []

    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {article.get('title', '')}")
        url, title, lines = fetch(article)
        if lines:
            deals.extend(extract(article, url, title, lines))
        time.sleep(REQUEST_DELAY_SECONDS)

    fresh_deals = deduplicate_deals(deals)
    # 本次完全沒有擷取到候選資料時，停止並保留舊 JSON，避免空結果覆蓋網站。
    if not fresh_deals:
        raise RuntimeError("本次沒有擷取到任何優惠候選資料；為避免清空網站資料，停止更新 deals.json。")
    # 只用本次成功擷取的資料重建，避免舊的錯誤/重複資料永久累積。
    final_deals = refresh_statuses(fresh_deals)

    # 店家排序讓 JSON 與前端資料較易檢查。
    store_order = ["7-ELEVEN", "全家", "萊爾富", "OKmart", "美廉社", "星巴克",
                   "路易莎", "85°C", "cama", "綜合／待確認"]
    final_deals.sort(key=lambda d: (
        store_order.index(d.get("store")) if d.get("store") in store_order else len(store_order),
        d.get("start_date") or "9999-99-99",
        d.get("offer", ""),
    ))

    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "disclaimer": (
            "資料由指定新聞文章與公開新聞搜尋結果自動擷取，可能漏抓或誤判。"
            "日期狀態依文章文字推算，不代表店家官方確認；"
            "日期不明或只有截止日的優惠列為待確認。"
            "實際優惠、適用門市、品項及兌換規則以店家公告為準。"
        ),
        "count": len(final_deals),
        "deals": final_deals,
    }

    # 先寫暫存檔再原子替換，避免程式中斷留下半份 JSON。
    temp_path = "deals.json.tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, "deals.json")

    counts = {
        status: sum(1 for deal in final_deals if deal.get("status") == status)
        for status in ("active", "verify", "upcoming", "expired")
    }
    print("\nSaved", len(final_deals), "candidate rows to deals.json")
    print("Active:", counts["active"])
    print("Needs verification:", counts["verify"])
    print("Upcoming:", counts["upcoming"])
    print("Expired:", counts["expired"])


if __name__ == "__main__":
    main()
