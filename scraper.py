#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
省咖啡｜優惠雷達 scraper.py

功能：
- 從 Google News RSS 搜尋咖啡優惠文章
- 解析文章中的多筆優惠
- 以段落標題及優惠文字判斷品牌
- 將日期不完整的優惠標示為 verify
- 以店家、優惠文字及起訖日期去重，保留不同日期的活動
- 輸出 GitHub Pages 使用的 deals.json

注意：
- 自動擷取無法保證涵蓋所有店家或所有優惠，請人工核對。
- 本程式會將新抓到的優惠與既有 deals.json 合併，避免搜尋漏抓造成舊優惠消失。
"""

import json
import re
import time
import html
from datetime import datetime, date, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests
import os
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


def extract(article, url, title, lines):
    results = []
    if not is_coffee_related(title + " " + " ".join(lines)):
        print("SKIP unrelated article:", title)
        return results

    current_store = ""
    for idx, original_line in enumerate(lines):
        line = original_line.strip()
        if not line:
            continue

        heading = heading_store_for_line(line)
        if heading:
            current_store = heading
            continue

        # 若本行不是優惠句，下一行若有日期有時仍屬同一優惠；
        # 因此只在本行有促銷關鍵字時建立紀錄，並附加下一行的日期文字。
        if not OFFER_RE.search(line) or not 5 <= len(line) <= 500:
            continue

        # 日期只優先採用本優惠同一行的日期。
        # 只有相鄰行明確像「活動期間／優惠期間／即日起」且不是另一項優惠時，
        # 才納入日期判斷，降低把其他優惠日期錯套過來的機率。
        date_context = line
        nearby = []
        for j in range(max(0, idx - 1), min(len(lines), idx + 2)):
            if j == idx:
                continue
            candidate = lines[j].strip()
            if OFFER_RE.search(candidate):
                continue
            explicit_period = re.search(
                r"(?:活動(?:期間|日期)|優惠期間|即日起|限定至|截止(?:日期)?|活動至)",
                candidate
            )
            has_date = DATE_RE.search(candidate) or SINGLE_DATE_RE.search(candidate)
            if explicit_period and has_date:
                nearby.append(candidate)
        if nearby:
            date_context = " ".join([line] + nearby)

        candidates = split_mixed_store_line(line)
        for line_store, offer_line in candidates:
            store = line_store or get_store(offer_line) or current_store or get_store(title)
            if not store:
                store = "綜合／待確認"

            parsed = parse_range(date_context)
            start = parsed[0] if parsed else None
            end = parsed[1] if parsed else None
            date_text = parsed[2] if parsed else ""
            start_iso = start.isoformat() if start else ""
            end_iso = end.isoformat() if end else ""

            # 僅截止日仍需確認；不能因為 end_date 未過期就當成 active。
            status = infer_status(start, end)

            results.append({
                "store": store,
                "offer": offer_line.strip(),
                "status": status,
                "start_date": start_iso,
                "end_date": end_iso,
                "date_text": date_text,
                "article_title": title,
                "article_url": url,
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


def deduplicate_deals(deals):
    """
    去重鍵包含日期：
    - 同店、同文字、同日期，即使來自不同文章也合併。
    - 活動日期不同，一律保留。
    - 不會用「只看店家」或「只看折扣關鍵字」的方式粗暴合併。
    """
    unique = {}
    for deal in deals:
        key = (
            deal.get("store", ""),
            normalize_offer(deal.get("offer", "")),
            deal.get("start_date", ""),
            deal.get("end_date", ""),
        )
        if key not in unique:
            unique[key] = deal
            continue

        old = unique[key]
        # 若先前版本缺資料，才由重複紀錄補上。
        for field in ("date_text", "article_title", "article_url", "published"):
            if not old.get(field) and deal.get(field):
                old[field] = deal[field]
        # 同一活動有一筆日期完整、另一筆日期不完整時，優先保留日期完整者。
        if old.get("status") == "verify" and deal.get("status") != "verify":
            old["status"] = deal["status"]
            old["start_date"] = deal.get("start_date", old.get("start_date", ""))
            old["end_date"] = deal.get("end_date", old.get("end_date", ""))

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
    # 合併舊資料：Google News 暫時漏抓、網站阻擋或解析失敗時，舊優惠不會整批消失。
    existing_deals = load_existing_deals("deals.json")
    final_deals = refresh_statuses(merge_existing_and_new(existing_deals, fresh_deals))

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
    # 關閉暫存檔後再替換正式檔案。
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