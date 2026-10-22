
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import time
import html
from datetime import datetime, date, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    )
}

MAX_ARTICLES = 40

# 直接加入你提供的中天新聞文章
SEED_ARTICLES = [
    {
        "title": "中天新聞咖啡優惠整理",
        "url": "https://ctinews.com/news/items/bKxrXQKYW9",
        "published": ""
    }
]

QUERIES = [
    'site:applealmond.com/posts 咖啡優惠',
    'site:nownews.com 超商咖啡優惠',
    'site:ctinews.com/news 咖啡優惠',
    'site:ctinews.com/news 超商咖啡 買一送一',
    '台灣超商咖啡優惠 7-ELEVEN 全家 萊爾富',
    '星巴克 路易莎 咖啡優惠 寄杯 買一送一',
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
    ("cama", r"\bcama\b"),
    ("全聯", r"全聯|大全聯"),
]

OFFER_RE = re.compile(
    r"買\s*[一1]\s*送\s*[一1]"
    r"|買\s*\d+\s*送\s*\d+"
    r"|第\s*二\s*杯"
    r"|第二杯"
    r"|任選\s*\d+\s*杯"
    r"|[兩二三四五六七八九十\d]+\s*杯\s*\d+\s*元"
    r"|寄杯"
    r"|折\s*扣"
    r"|優惠價"
    r"|組合價"
    r"|現折"
    r"|咖啡.*\d+\s*元"
    r"|大杯.{0,15}\d+\s*元"
)


# 支援西元年份（2026）與民國年份（115）
DATE_RE = re.compile(
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
    r"\s*(?:至|到|～|~|－|—|-|–)\s*"
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
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    result = []

    for item in root.findall(".//item"):
        title = html.unescape(item.findtext("title") or "")
        link = item.findtext("link") or ""
        published = item.findtext("pubDate") or ""
        if link:
            result.append({
                "title": title,
                "url": link,
                "published": published
            })

    return result

def fetch(article):
    try:
        r = requests.get(
            article["url"],
            headers=HEADERS,
            timeout=30,
            allow_redirects=True
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 優先取文章正文，移除不相關區域
        for tag in soup([
            "script", "style", "nav", "footer",
            "header", "aside", "form", "noscript"
        ]):
            tag.decompose()

        root = (
            soup.find("article")
            or soup.find("main")
            or soup.find(attrs={"itemprop": "articleBody"})
            or soup.body
            or soup
        )

        lines = [
            re.sub(r"\s+", " ", line).strip(" •◾▪●　\t")
            for line in root.get_text("\n", strip=True).splitlines()
        ]
        lines = [line for line in lines if line]

        title = article["title"]
        if soup.title:
            title = soup.title.get_text(" ", strip=True)

        print("FETCH OK:", r.url, "lines:", len(lines))
        return r.url, title, lines

    except Exception as exc:
        print("FETCH ERROR:", article["url"], str(exc))
        return article["url"], article["title"], []



def make_date(year, month, day, fallback_year):
    """轉換西元或民國日期；日期不合法時回傳 None。"""
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
    """解析日期區間、即日起至日期，以及只有截止日的文字。"""
    # 即日起至 115/11/10：起日採程式執行當天，但仍需人工確認優惠真實性。
    if "即日起" in text:
        match = SINGLE_DATE_RE.search(text)
        if match:
            year, month, day = match.groups()
            end = make_date(year, month, day, TODAY.year)
            if end and end >= TODAY:
                return TODAY, end, match.group(0)

    # 一般起訖日期，例如 10/14~10/27、2026/9/9~11/3。
    match = DATE_RE.search(text)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()
        start = make_date(y1, m1, d1, TODAY.year)
        end = make_date(y2 or y1, m2, d2, TODAY.year)
        if start and end:
            if not y1 and not y2 and end < start and start.month >= 11 and end.month <= 2:
                end = date(start.year + 1, end.month, end.day)
            if end >= start:
                return start, end, match.group(0)

    # 只有截止日：起始日未知，所以回傳 start=None，status 保持 verify。
    cutoff = re.search(
        r"(?:至|到|截止(?:日期)?(?:為|：|:)?|限定至)\s*"
        r"((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)",
        text
    )
    if not cutoff:
        cutoff = re.search(
            r"((?:(?:20\d{2}|1\d{2})\s*[年/.-]\s*)?\d{1,2}\s*[月/.-]\s*\d{1,2}\s*日?)\s*前限定",
            text
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
    """只在優惠文字明確指向單一品牌時分類，避免跨品牌誤判。"""
    matches = []

    for name, pattern in STORE_PATTERNS:
        if re.search(pattern, text, re.I):
            matches.append(name.strip())

    # 沒有品牌，或同時出現多個品牌，都先列為待確認
    if len(matches) != 1:
        return "綜合／待確認"

    return matches[0]


def is_coffee_related(text):
    # 避免大量無關科技、汽車等新聞進入結果
    coffee_words = (
        "咖啡", "cafe", "café", "星巴克", "路易莎",
        "萊爾富", "美廉社", "cama", "寄杯"
    )
    t = text.lower()
    return any(word.lower() in t for word in coffee_words)




def extract(article, url, title, lines):
    results = []
    full_text = " ".join(lines)
    if not is_coffee_related(title + " " + full_text):
        print("SKIP unrelated article:", title)
        return results

    current_store = ""
    heading_map = {
        "星巴克": "星巴克", "Starbucks": "星巴克",
        "7-11": "7-ELEVEN", "7－11": "7-ELEVEN",
        "7-ELEVEN": "7-ELEVEN", "7-Eleven": "7-ELEVEN",
        "全家": "全家", "萊爾富": "萊爾富", "路易莎": "路易莎",
        "美廉社": "美廉社", "OKmart": "OKmart", "cama": "cama",
    }

    for original_line in lines:
        line = original_line.strip()
        heading_line = re.sub(r"（.*?）|\(.*?\)", "", line).strip(" ：:　")
        if heading_line in heading_map:
            current_store = heading_map[heading_line]
            continue

        # 同一行同時提到全家與萊爾富時拆開，避免跨品牌合併。
        if "全家推出" in line and "萊爾富則" in line:
            parts = line.split("萊爾富則", 1)
            family_part = re.sub(r"^咖啡控快搶！", "", parts[0]).strip()
            hilife_part = parts[1].strip()
            candidates = []
            if family_part:
                candidates.append(("全家", family_part))
            if hilife_part:
                candidates.append(("萊爾富", hilife_part))
        else:
            candidates = [(current_store, line)]

        for heading_store, offer_line in candidates:
            if not OFFER_RE.search(offer_line) or not 5 <= len(offer_line) <= 300:
                continue

            parsed = parse_range(offer_line)
            status = "verify"
            start_iso = ""
            end_iso = ""
            date_text = ""
            if parsed:
                start, end, date_text = parsed
                if start:
                    start_iso = start.isoformat()
                if end:
                    end_iso = end.isoformat()
                if start and end and start <= TODAY <= end:
                    status = "active"
                elif start and TODAY < start:
                    status = "upcoming"
                elif end and TODAY > end:
                    status = "expired"
                # 只有截止日而沒有起始日，一律保留 verify，避免誤標為有效。

            detected_store = get_store(offer_line)
            store = heading_store or detected_store
            if detected_store != "綜合／待確認":
                store = detected_store

            results.append({
                "store": store or "綜合／待確認",
                "offer": offer_line,
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
    return results


def normalize_offer(offer):
    """統一空白與標點，保留價格、杯數等重要資訊。"""
    normalized = re.sub(r"[\s　，。；：、！!？?（）()\[\]【】]", "", offer)
    # 不限定星期幾：同樣的咖啡日加價換一杯活動使用穩定去重鍵。
    if "咖啡日" in offer and re.search(r"加\s*10\s*元.{0,8}多\s*1\s*杯", offer):
        return "全家咖啡日_加10元多1杯"
    return normalized

def main():
    found = list(SEED_ARTICLES)

    for query in QUERIES:
        try:
            items = rss(query)
            print("RSS OK:", query, "items:", len(items))
            found.extend(items)
        except Exception as exc:
            print("RSS ERROR:", query, str(exc))

    # 依文章網址去重
    unique_articles = {}
    for article in found:
        unique_articles.setdefault(article["url"], article)

    articles = list(unique_articles.values())[:MAX_ARTICLES]
    deals = []

    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {article['title']}")
        url, title, lines = fetch(article)

        if lines:
            deals.extend(extract(article, url, title, lines))

        time.sleep(0.5)

   
    unique_deals = {}
    for deal in deals:
        key = (
            deal["store"],
            normalize_offer(deal["offer"]),
            deal["article_url"]
        )
        unique_deals.setdefault(key, deal)

    final_deals = list(unique_deals.values())

    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "disclaimer": (
            "資料由公開新聞文章自動擷取，可能漏抓或誤判。"
            "日期狀態僅依文章文字推算，不代表店家官方確認；"
            "日期不明或只有截止日的優惠仍需人工確認。"
            "實際優惠、適用門市、品項及兌換規則以店家官方公告為準。"
        ),
        "count": len(final_deals),
        "deals": final_deals
    }

    with open("deals.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    active_count = sum(d["status"] == "active" for d in final_deals)
    verify_count = sum(d["status"] == "verify" for d in final_deals)

    print("Saved", len(final_deals), "candidate rows to deals.json")
    print("Active:", active_count)
    expired_count = sum(d["status"] == "expired" for d in final_deals)
    print("Needs verification:", verify_count)
    print("Expired:", expired_count)

if __name__ == "__main__":
    main()