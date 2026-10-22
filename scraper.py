
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

# =========================================================
# 基本設定
# =========================================================

TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
    )
}

MAX_ARTICLES = 40
REQUEST_TIMEOUT = 25

SEED_ARTICLES = [
    {
        "title": "中天新聞咖啡優惠整理",
        "url": "https://ctinews.com/news/items/bKxrXQKYW9",
        "published": "",
    }
]

QUERIES = [
    "site:applealmond.com/posts 咖啡優惠",
    "site:nownews.com 超商咖啡優惠",
    "site:ctinews.com/news 咖啡優惠",
    "site:ctinews.com/news 超商咖啡 買一送一",
    "台灣超商咖啡優惠 7-ELEVEN 全家 萊爾富",
    "星巴克 路易莎 咖啡優惠 寄杯 買一送一",
]

STORE_PATTERNS = [
    ("7-ELEVEN", r"7\s*[-－]?\s*ELEVEN|7-11|CITY\s*CAFE"),
    ("全家", r"全家|Let's\s*Café|Let's\s*Cafe"),
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
    r"|第二杯|第\s*二\s*杯"
    r"|任選\s*\d+\s*杯"
    r"|[兩二三四五六七八九十\d]+\s*杯\s*\d+\s*元"
    r"|寄杯|折\s*扣|優惠價|組合價|現折"
    r"|咖啡.{0,25}\d+\s*元"
    r"|大杯.{0,25}\d+\s*元"
    r"|特大杯.{0,25}\d+\s*元",
    re.I,
)

DATE_TOKEN = (
    r"(?:(20\d{2}|1\d{2})\s*[年/.-]\s*)?"
    r"(\d{1,2})\s*[月/.-]\s*(\d{1,2})\s*日?"
)

DATE_RANGE_RE = re.compile(
    DATE_TOKEN
    + r"\s*(?:至|到|～|~|－|—|-|–)\s*"
    + DATE_TOKEN
)

SINGLE_DATE_RE = re.compile(DATE_TOKEN)

# =========================================================
# 日期處理
# =========================================================

def make_date(year, month, day, fallback_year=None):
    """支援西元與民國年份；不合法日期回傳 None。"""
    try:
        if year:
            y = int(year)
            if 1 <= y <= 191:
                y += 1911
        else:
            y = fallback_year or TODAY.year

        return date(y, int(month), int(day))
    except (ValueError, TypeError):
        return None


def infer_yearless_range(m1, d1, m2, d2):
    """
    推測沒有年份的起訖日期。
    例如目前為 2026/10，7/23～12/31 應推定為 2026 年。
    跨年區間則允許結束日期落在下一年。
    """
    start_month = int(m1)
    start_day = int(d1)
    end_month = int(m2)
    end_day = int(d2)

    start_year = TODAY.year

    # 若整個區間看起來是去年活動，且已結束，
    # 不要把它自動推成今年的未來活動。
    start = date(start_year, start_month, start_day)
    end = date(start_year, end_month, end_day)

    if end < start:
        if start_month >= 10 and end_month <= 3:
            end = date(start_year + 1, end_month, end_day)
        else:
            # 較可能是跨年或日期文字不完整，交由人工確認。
            return None, None

    return start, end


def parse_range(text):
    """
    回傳 (start_date, end_date, 原始日期文字)。

    只有截止日期、沒有起始日期的優惠不會直接判定有效。
    「即日起」以程式執行當天為起始日，但仍需人工核實。
    """
    if "即日起" in text:
        match = SINGLE_DATE_RE.search(text)
        if match:
            year, month, day = match.groups()
            end = make_date(year, month, day, TODAY.year)

            if end:
                return TODAY, end, match.group(0)

    match = DATE_RANGE_RE.search(text)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()

        if y1:
            start = make_date(y1, m1, d1, TODAY.year)
        else:
            start = None

        if y2:
            end = make_date(y2, m2, d2, TODAY.year)
        elif y1:
            end = make_date(y1, m2, d2, TODAY.year)
        else:
            start, end = infer_yearless_range(m1, d1, m2, d2)

        if start is None and not y1 and end is None:
            return None

        if start and end:
            if end < start:
                # 明確年份下，無法合理解釋的區間不自動修正。
                return None

            return start, end, match.group(0)

    # 只有截止日期：保留待確認，不自行推定開始日期。
    cutoff = re.search(
        r"(?:至|到|截止(?:日期)?(?:為|：|:)?|限定至)\s*"
        + DATE_TOKEN,
        text,
    )

    if cutoff:
        year, month, day = cutoff.groups()
        end = make_date(year, month, day, TODAY.year)
        if end:
            return None, end, cutoff.group(0)

    return None


def get_status(start, end):
    """依照日期判斷狀態；日期不完整時一律待確認。"""
    if not start or not end:
        return "verify"

    if end < start:
        return "verify"

    if TODAY < start:
        return "upcoming"

    if TODAY > end:
        return "expired"

    return "active"


# =========================================================
# 品牌、商品分類與去重
# =========================================================

def get_store(text):
    matches = []

    for name, pattern in STORE_PATTERNS:
        if re.search(pattern, text, re.I):
            matches.append(name)

    matches = list(dict.fromkeys(matches))

    if len(matches) == 1:
        return matches[0]

    return "綜合／待確認"


def get_category(text):
    """分類為咖啡、茶飲、其他飲品或待確認。"""
    t = text.lower()

    tea_words = (
        "奶茶", "紅茶", "綠茶", "烏龍茶", "焙茶",
        "抹茶", "茶飲", "let's tea", "珍珠",
    )

    coffee_words = (
        "咖啡", "美式", "拿鐵", "café", "cafe",
        "咖啡豆", "寄杯", "city cafe", "hi cafe",
        "星巴克", "路易莎", "cama",
    )

    other_words = (
        "果汁", "果茶", "氣泡飲", "冰沙", "星沁爽",
        "牛奶", "撞奶",
    )

    # 同一優惠可能同時包含咖啡與茶飲，優先保留混合分類。
    has_tea = any(word in t for word in tea_words)
    has_coffee = any(word in t for word in coffee_words)

    if has_tea and has_coffee:
        return "混合飲品"
    if has_coffee:
        return "咖啡"
    if has_tea:
        return "茶飲"
    if any(word in t for word in other_words):
        return "其他飲品"

    return "待確認"


def normalize_offer(offer):
    """清除空白與一般標點，保留價格、杯數與品項。"""
    return re.sub(
        r"[\s　，。；：、！!？?（）()\[\]【】]",
        "",
        offer,
    ).lower()


def is_relevant(text):
    """避免把與咖啡或飲品無關的文章列為優惠。"""
    keywords = (
        "咖啡", "cafe", "café", "星巴克", "路易莎",
        "萊爾富", "美廉社", "cama", "寄杯",
        "city cafe", "hi cafe", "超商咖啡",
        "let's café", "let's cafe", "let's tea",
        "焙茶", "抹茶歐蕾",
    )
    t = text.lower()
    return any(word in t for word in keywords)


# =========================================================
# RSS 與文章擷取
# =========================================================

def rss(query):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    results = []

    for item in root.findall(".//item"):
        title = html.unescape(item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate") or ""

        if link:
            results.append({
                "title": title,
                "url": link,
                "published": published,
            })

    return results


def fetch(article):
    try:
        response = requests.get(
            article["url"],
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup([
            "script", "style", "nav", "footer", "header",
            "aside", "form", "noscript",
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

        print("FETCH OK:", response.url, "lines:", len(lines))
        return response.url, title, lines

    except Exception as exc:
        print("FETCH ERROR:", article["url"], str(exc))
        return article["url"], article["title"], []


# =========================================================
# 優惠擷取
# =========================================================

HEADINGS = {
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


def split_mixed_line(line):
    """
    針對已知的全家／萊爾富混合句型拆分。
    其他多品牌句型不猜測，避免把錯誤品牌寫進資料。
    """
    if "全家推出" in line and "萊爾富則" in line:
        parts = line.split("萊爾富則", 1)
        family_part = re.sub(r"^咖啡控快搶！", "", parts[0]).strip()
        hilife_part = parts[1].strip()

        result = []
        if family_part:
            result.append(("全家", family_part))
        if hilife_part:
            result.append(("萊爾富", hilife_part))
        return result

    return [(None, line)]


def extract(article, url, title, lines):
    results = []

    if not is_relevant(title + " " + " ".join(lines)):
        print("SKIP unrelated article:", title)
        return results

    current_store = ""

    for original_line in lines:
        line = original_line.strip()

        # 辨認獨立品牌標題。
        heading_line = re.sub(r"（.*?）|\(.*?\)", "", line)
        heading_line = heading_line.strip(" ：:　")

        if heading_line in HEADINGS:
            current_store = HEADINGS[heading_line]
            continue

        for split_store, offer_line in split_mixed_line(line):
            if not OFFER_RE.search(offer_line):
                continue

            if not 5 <= len(offer_line) <= 350:
                continue

            if not is_relevant(offer_line):
                continue

            parsed = parse_range(offer_line)

            start = None
            end = None
            date_text = ""

            if parsed:
                start, end, date_text = parsed

            status = get_status(start, end)

            # 優先採用已知標題品牌。
            # 若同一優惠句明確提到另一品牌，則標記為待確認，
            # 不讓整篇新聞的其他品牌覆蓋目前品牌。
            detected_store = get_store(offer_line)

            if split_store:
                store = split_store
            elif detected_store != "綜合／待確認":
                store = detected_store
            elif current_store:
                store = current_store
            else:
                store = "綜合／待確認"

            # 如果文章段落同時提到多個品牌，不能可靠歸屬時先待確認。
            brand_count = sum(
                1 for _, pattern in STORE_PATTERNS
                if re.search(pattern, offer_line, re.I)
            )
            if brand_count > 1 and not split_store:
                store = "綜合／待確認"
                status = "verify"

            results.append({
                "store": store,
                "offer": offer_line,
                "category": get_category(offer_line),
                "status": status,
                "start_date": start.isoformat() if start else "",
                "end_date": end.isoformat() if end else "",
                "date_text": date_text,
                "article_title": title,
                "article_url": url,
                "published": article.get("published", ""),
                "source": "新聞文章自動擷取",
                "needs_check": True,
            })

    return results


# =========================================================
# 清理資料與輸出 JSON
# =========================================================

def deduplicate(deals):
    """
    相同店家、相同優惠文字、相同日期才合併。
    不同價格、杯數、品項或活動日期都保留。
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
        else:
            # 優先保留有日期、原文較完整的資料。
            old = unique[key]
            old_score = (
                bool(old.get("start_date")),
                bool(old.get("end_date")),
                len(old.get("offer", "")),
            )
            new_score = (
                bool(deal.get("start_date")),
                bool(deal.get("end_date")),
                len(deal.get("offer", "")),
            )

            if new_score > old_score:
                unique[key] = deal

    return list(unique.values())


def main():
    found = list(SEED_ARTICLES)

    for query in QUERIES:
        try:
            items = rss(query)
            print("RSS OK:", query, "items:", len(items))
            found.extend(items)
        except Exception as exc:
            print("RSS ERROR:", query, str(exc))

    # 同一網址只抓一次。
    unique_articles = {}
    for article in found:
        url = article.get("url", "").strip()
        if url:
            unique_articles.setdefault(url, article)

    articles = list(unique_articles.values())[:MAX_ARTICLES]
    deals = []

    for i, article in enumerate(articles, 1):
        print(f"[{i}/{len(articles)}] {article.get('title', '')}")

        url, title, lines = fetch(article)

        if lines:
            deals.extend(extract(article, url, title, lines))

        time.sleep(0.5)

    final_deals = deduplicate(deals)

    # 讓前端可以直接顯示有效優惠，再依店家及活動日期排序。
    store_order = {
        "7-ELEVEN": 1,
        "全家": 2,
        "萊爾富": 3,
        "OKmart": 4,
        "美廉社": 5,
        "星巴克": 6,
        "路易莎": 7,
        "cama": 8,
    }

    status_order = {
        "active": 1,
        "upcoming": 2,
        "verify": 3,
        "expired": 4,
    }

    final_deals.sort(key=lambda d: (
        status_order.get(d.get("status"), 9),
        store_order.get(d.get("store"), 99),
        d.get("end_date") or "9999-12-31",
        d.get("offer", ""),
    ))

    active_count = sum(d["status"] == "active" for d in final_deals)
    upcoming_count = sum(d["status"] == "upcoming" for d in final_deals)
    verify_count = sum(d["status"] == "verify" for d in final_deals)
    expired_count = sum(d["status"] == "expired" for d in final_deals)

    data = {
        "updated_at": datetime.now(TZ).isoformat(),
        "today": TODAY.isoformat(),
        "timezone": "Asia/Taipei",
        "disclaimer": (
            "資料由公開新聞文章自動擷取，可能漏抓、重複或誤判。"
            "日期狀態僅依文章文字推算，不代表店家官方確認。"
            "日期不明、品牌不明或只有截止日的優惠會列為待確認。"
            "實際優惠、適用門市、品項、價格及兌換規則，"
            "請以店家官方公告為準。"
        ),
        "count": len(final_deals),
        "counts": {
            "active": active_count,
            "upcoming": upcoming_count,
            "verify": verify_count,
            "expired": expired_count,
        },
        "deals": final_deals,
    }

    with open("deals.json", "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    print("=" * 45)
    print("Saved", len(final_deals), "deals to deals.json")
    print("Today:", TODAY.isoformat())
    print("Active:", active_count)
    print("Upcoming:", upcoming_count)
    print("Needs verification:", verify_count)
    print("Expired:", expired_count)
    print("=" * 45)


if __name__ == "__main__":
    main()
