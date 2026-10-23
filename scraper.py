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
URL_COSMO = "