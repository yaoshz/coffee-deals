
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

DATE_RE = re.compile(
    r"(?:(20\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
    r"\s*(?:至|到|～|~|－|—|-|–|起至|起～)\s*"
    r"(?:(20\d{2})\s*[年/.-]\s*)?"
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
    try:
        y = int(year) if year else fallback_year
        return date(y, int(month), int(day))
    except (ValueError, TypeError):
        return None

def parse_range(text):
    match = DATE_RE.search(text)
    if not match:
        return None

    y1, m1, d1, y2, m2, d2 = match.groups()

    start = make_date(y1, m1, d1, TODAY.year)
    end = make_date(y2 or y1, m2, d2, TODAY.year)

    if start and end:
        if not y2 and end < start and start.month >= 11 and end.month <= 2:
            end = date(start.year + 1, end.month, end.day)

        if end >= start:
            return start, end, match.group(0)

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
    seen_family_coffee_day = False

    # 只辨識單獨出現的品牌標題
    heading_map = {
        "星巴克": "星巴克",
        "Starbucks": "星巴克",
        "7-11": "7-ELEVEN",
        "7－11": "7-ELEVEN",
        "7-ELEVEN": "7-ELEVEN",
        "7-Eleven": "7-ELEVEN",
        "全家": "全家",
        "萊爾富": "萊爾富",
        "路易莎": "路易莎",
        "美廉社": "美廉社",
        "OKmart": "OKmart",
        "cama": "cama",
    }

    for original_line in lines:
        line = original_line.strip()

        # 移除常見圖片說明，避免干擾品牌判斷
        heading_line = re.sub(
            r"（.*?）|\(.*?\)",
            "",
            line
        ).strip(" ：:　")

        if heading_line in heading_map:
            current_store = heading_map[heading_line]
            continue

        # 將文章開頭同時提到全家與萊爾富的優惠分開
        if "全家推出" in line and "萊爾富則" in line:
            parts = line.split("萊爾富則", 1)

            family_part = parts[0].strip()
            hilife_part = parts[1].strip()

            family_part = re.sub(
                r"^咖啡控快搶！",
                "",
                family_part
            ).strip()

            candidate_lines = []

            if family_part:
                candidate_lines.append(
                    ("全家", family_part)
                )

            if hilife_part:
                candidate_lines.append(
                    ("萊爾富", hilife_part)
                )
        else:
            candidate_lines = [(current_store, line)]

        # 逐筆處理優惠
        for heading_store, offer_line in candidate_lines:

            # 全家咖啡日只保留第一筆描述，不限定星期幾
            if (
                heading_store == "全家"
                and re.search(
                    r"週[一二三四五六日天]咖啡日|咖啡日",
                    offer_line
                )
            ):
                if seen_family_coffee_day:
                    continue

                seen_family_coffee_day = True

            if not OFFER_RE.search(offer_line):
                continue

            if len(offer_line) > 300 or len(offer_line) < 5:
                continue

            parsed = parse_range(offer_line)

            status = "verify"
            start_iso = ""
            end_iso = ""
            date_text = ""

            if parsed:
                start, end, date_text = parsed
                start_iso = start.isoformat()
                end_iso = end.isoformat()

                if start <= TODAY <= end:
                    status = "active"
                elif TODAY < start:
                    status = "upcoming"
                else:
                    status = "expired"

            detected_store = get_store(offer_line)

            # 優先採用文章品牌標題；
            # 若優惠文字明確指出另一品牌，則採用文字中的品牌
            if heading_store:
                store = heading_store

                if detected_store != "綜合／待確認":
                    store = detected_store
            else:
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
        # 統一空白與常見標點，減少格式不同造成的重複
        normalized_offer = re.sub(
            r"[\s　，。；：、！!？?（）()\[\]【】]",
            "",
            deal["offer"]
        )

        key = (
            deal["store"],
            normalized_offer,
            deal["article_url"]
        )

        unique_deals.setdefault(key, deal)

    final_deals = list(unique_deals.values())

    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "disclaimer": (
            "資料由公開新聞文章自動擷取，可能漏抓或誤判。"
            "只有可辨識明確起訖日期且包含今天的優惠標示為有效；"
            "日期不明者請點原文確認。實際優惠依店家官方公告為準。"
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
    print("Needs verification:", verify_count)

if __name__ == "__main__":
    main()
