#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""獨立探測 7-ELEVEN／全家官方網站的靜態 HTTP 可讀性。

此工具不屬於 scraper.py 主流程。403/429/JS 空殼只記錄在報告中，不嘗試繞過防護。
可用 OFFICIAL_PROBE_URLS 以分號指定額外官方活動頁網址。
"""
from __future__ import annotations
import argparse
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TZ = timezone(timedelta(hours=8))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CoffeeDealsSourceProbe/1.0)",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}
BASES = {
    "7-ELEVEN": ["https://www.7-11.com.tw/"],
    "全家": ["https://www.family.com.tw/"],
}
LINK_HINT = re.compile(r"活動|優惠|咖啡|cafe|coffee|campaign|event|marketing|news|product", re.I)
KEYWORDS = ("咖啡", "優惠", "CITY CAFE", "Let's Cafe", "隨買跨店取", "活動")


def inspect_url(session: requests.Session, brand: str, url: str, timeout: int = 12) -> dict:
    record = {"brand": brand, "url": url, "tested_at": datetime.now(TZ).isoformat()}
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        content = response.content or b""
        soup = BeautifulSoup(content, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        text = " ".join(soup.stripped_strings)
        record.update({
            "final_url": response.url,
            "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type", ""),
            "response_bytes": len(content),
            "text_length": len(text),
            "keyword_hits": [word for word in KEYWORDS if word.lower() in text.lower()],
            "js_shell_suspected": len(text) < 120 and bool(re.search(rb"id=[\"'](?:app|root)[\"']", content, re.I)),
            "result": "readable" if response.ok and len(text) >= 120 else "blocked_or_shell" if response.status_code in (403, 429) or len(text) < 120 else "http_error",
        })
        record["candidate_links"] = [
            urljoin(response.url, a.get("href", ""))
            for a in soup.find_all("a", href=True)
            if LINK_HINT.search(" ".join([a.get_text(" ", strip=True), a.get("href", "")]))
            and (urlparse(urljoin(response.url, a["href"])).hostname or "").removeprefix("www.").endswith(
                (urlparse(response.url).hostname or "").removeprefix("www.")
            )
        ][:20]
    except requests.RequestException as exc:
        record.update({"http_status": None, "response_bytes": 0, "text_length": 0,
                       "result": "request_error", "error": str(exc)[:500], "candidate_links": []})
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="official_source_probe.json")
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--strict", action="store_true", help="有來源不可讀時回傳非零；預設只產生報告")
    args = parser.parse_args()
    targets = {brand: list(urls) for brand, urls in BASES.items()}
    extra = [x.strip() for x in os.getenv("OFFICIAL_PROBE_URLS", "").split(";") if x.strip()]
    for url in extra:
        host = urlparse(url).netloc.lower()
        brand = "7-ELEVEN" if "7-11.com.tw" in host else "全家" if "family.com.tw" in host else "custom"
        targets.setdefault(brand, []).append(url)
    session = requests.Session()
    session.headers.update(HEADERS)
    records = []
    for brand, urls in targets.items():
        seen = set()
        queue = [(url, "configured") for url in urls]
        # 先探測官方首頁，再最多追蹤 8 個站內活動／咖啡候選頁；不執行 JS、不繞過 WAF。
        while queue and len(seen) < 9:
            url, discovered_from = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            record = inspect_url(session, brand, url, args.timeout)
            record["discovered_from"] = discovered_from
            records.append(record)
            for candidate in record.get("candidate_links", []):
                if candidate not in seen and len(seen) + len(queue) < 9:
                    queue.append((candidate, url))
    report = {"tested_at": datetime.now(TZ).isoformat(), "mode": "standalone_non_blocking_probe",
              "summary": {"total": len(records), "readable": sum(x["result"] == "readable" for x in records),
                          "blocked_or_shell": sum(x["result"] == "blocked_or_shell" for x in records),
                          "request_error": sum(x["result"] == "request_error" for x in records)},
              "results": records,
              "note": "此報告只代表目前 Runner 的 HTTP 可讀性；403/429 不代表網站永遠不可用。未嘗試繞過網站防護。"}
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 1 if args.strict and any(x["result"] != "readable" for x in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
