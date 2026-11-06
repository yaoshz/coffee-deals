# 省咖啡 v6.15 修正版

## v6.15：修復全聯 OFF COFFEE 自帶杯優惠遭過濾的問題

- `split_compound_offer()` 的商品白名單加入英文單字 `\bcoffee\b`。
- `is_non_offer_record()` 的 `valid_products` 加入英文單字 `\bcoffee\b`。
- 不把「全聯／PX Mart」品牌名稱當成飲品品項白名單，避免放寬過濾器造成非優惠資料誤收。
- 新增兩項回歸測試：確認全聯自帶杯卡片通過單筆過濾，並能完整通過 `deduplicate_deals()`。
- `deals.json` 補入一筆 OFF COFFEE 自備環保杯折 5 元資料，狀態為 `verify`，起訖日期留空。
- 版號更新為 v6.15；保留既有 v6.14 全聯來源、PXGo 分批取、入口及三語設定。

## 測試

執行：`python -m unittest -v test_scraper_dedup.py`

本版測試涵蓋正則過濾、完整去重流程、資料快照筆數與狀態統計、前端版號及既有來源功能。

---

# 省咖啡｜優惠雷達 v6.13

## 本版重點

- **逐來源動態文章發現**：新增 NOWnews、Yahoo 新聞／Yahoo 股市、蘋果仁、中天、Cosmopolitan 的來源限定 Google News RSS 搜尋；每個來源各自記錄查詢成功率與新文章數。
- **官方來源補充**：保留 NOWnews 生活分類、85°C 官方消息列表、路易莎官方消息列表入口。官方列表和 RSS 發現彼此補充，不依賴固定文章 ID。
- **容錯隔離**：每個列表／RSS 查詢獨立執行；單一來源封鎖、逾時或改版，不會中止其他來源。文章仍須成功開啟原文，才會進入正文解析。
- **優惠資料品質**：保留原有多優惠拆分、日期解析、通路區隔、跨來源去重、舊資料保護與安全寫檔。
- **Facebook 限制**：不把一般 Facebook 粉專頁當成可靠的匿名爬取入口。品牌貼文可由搜尋引擎索引作為發現線索，但不保證每篇都能索引或讀取；穩定自動化仍需 Meta API 權限，或人工核對後匯入。
- **測試日期固定**：舊快照回歸測試固定使用 2026-10-23 作為測試基準，避免日期推移造成舊測試案例失效；正式程式仍使用台灣當日日期。

## 來源與限制

| 來源 | 動態發現方式 | 備註 |
|---|---|---|
| NOWnews | 生活分類列表 + 來源限定 RSS | 文章列表 DOM 變更時查看 `listing_discovery` |
| Yahoo 新聞／股市 | 來源限定 RSS 搜尋 | RSS 結果仍需追蹤跳轉至原文 |
| 蘋果仁 | 來源限定 RSS 搜尋 | 非官方 API，可能受索引延遲影響 |
| 中天新聞 | 來源限定 RSS 搜尋 | 非官方 API，可能受索引延遲影響 |
| Cosmopolitan | 來源限定 RSS 搜尋 | 非官方 API，可能受索引延遲影響 |
| 85°C | 官方消息列表 + 來源限定 RSS | Facebook 貼文非保證來源 |
| 路易莎 | 官方消息列表 + 來源限定 RSS | Facebook 貼文非保證來源 |
| 星巴克、7-ELEVEN、全家、萊爾富 | 來源限定 RSS 搜尋 | 若官方公告未被索引，仍可能漏抓 |

Google News RSS 是文章發現補充機制，不是各媒體的官方 API，也不保證即時、完整或每篇都能成功解析。Facebook 搜尋結果只能作為線索，不代表已讀取官方貼文全文。

## 部署

將 `scraper.py`、`deals.json`、`index.html`、`requirements.txt` 和 `test_scraper_dedup.py` 覆蓋到 GitHub 專案。保留原有 `.github/workflows/update-coffee-deals.yml`。

完成覆蓋後，在 GitHub Actions 手動執行更新工作流程。檢查 `scrape_report`：

- `listing_discovery`：NOWnews、85°C、路易莎官方列表是否成功。
- `source_rss_discovery`：逐來源 RSS 查詢成功率、搜尋結果數與去重後新文章數。
- `articles_fetched_successfully`：成功開啟原文的文章數。
- `articles_failed_or_low_content`：無法讀取的文章數。

## 測試

```bash
python -m unittest -v test_scraper_dedup.py
python -m py_compile scraper.py
python -m json.tool deals.json > /dev/null
```

本次離線回歸測試涵蓋既有優惠解析／去重案例、逐來源 RSS 成功與失敗隔離、文章 URL 去重、NOWnews 動態文章連結解析，以及 2026-10-31 到期優惠在 2026-11-06 不得標為有效。

## 重要限制

- 本次測試為離線測試，沒有宣稱已在 GitHub Actions 或各網站完成即時全站抓取。
- 動態發現能降低固定文章 ID 漏抓問題，但無法保證搜尋引擎已索引所有新文章。
- 85°C／路易莎 2026-10-31 截止的舊活動應依目前日期顯示為過期，不應當作本週有效優惠。


## v6.14 全聯（PX Mart）補強

- 新增全聯 OFF COFFEE／分批取的 Google News RSS 動態發現查詢。
- 將「分批取」加入線上通路辨識，避免與門市優惠混淆。
- 新增全聯官方入口與繁中／英文／泰文名稱。
- 新增 OFF COFFEE 自帶杯優惠保底。注意：全聯目前官方品牌頁列示折 5 元；歷史 8 元是舊活動，不再當作現行優惠。官方頁未標截止日，因此資料列為日期待確認，不虛構有效期限。
- 補入 2026/10/24–10/26 精品美式 9 杯 199 元、小農拿鐵 6 杯 199 元兩筆歷史分批取優惠；截至 2026/11/06 均標示過期。
- 增加 5 項 PX Mart 專屬回歸測試。
