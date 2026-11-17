# 省咖啡｜優惠雷達 v6.19

## v6.19 追加修補（2026-11-17）

本版重點是**動態發現新文章、保留媒體小標、正確拆出商品／日期／優惠**，並非每天手動加入固定新聞 URL。

- 直接列表新增 Cosmopolitan 嬌點話題、ETtoday 民生消費、星巴克台灣活動頁；有 keyword 篩選與逐來源報告，任何一個列表失敗不阻擋其他來源。
- Cosmopolitan 支援 `/g數字/` 圖集文章，補齊 `br` 換行、Hearst DOM 內容區以及「商品名／活動日期／買一送一」三個相鄰段落的合併解析。
- NOWnews、ETtoday 通用支援 `🟡`、`📍`、`◾`、`★`、`■` 等段落符號，保留品牌、通路和活動日期上下文；支援 `LINE禮物（7-11電子票券）` 作為 7-ELEVEN 品牌小標。
- `split_compound_offer()` 不再用頓號分開同一句的美式／拿鐵，避免只保留一個商品。
- 新增 `test_v619_regressions.py`（以媒體版型建立的**模擬 HTML** 回歸測試，而非完整新聞原始 HTML）。三個指定新聞網址不會被塞進日常 `SEED_ARTICLES`。
- **已完成 150 項離線測試**；沒有在 GitHub Actions 上對三篇新聞進行真實下載驗收，且 ETtoday 在本次網路檢查中無法直接開啟，不能保證其來源一定可用。
- **重要：** 本 ZIP 的 `deals.json` 為前一輪保存的快照（`processing_version` 可能仍顯示 v6.18.1）。請部署後手動跑 Actions 生成新的 v6.19 快照，別誤認 ZIP 裡的舊快照已更新優惠。

### 上線後請檢查

1. `deals.json` 的 `processing_version` 是否更新為 `v6.19`，`updated_at` 是否為本次執行時間。
2. `scrape_report.listing_discovery` 中的 `cosmo`、`ettoday`、`starbucks` 是否有 `ok` 及 `discovered`；若 `ok=true, discovered=0`，可能是頁面未提供新優惠連結或版型變更。
3. 在 `deals` 搜尋 `family-mart-1117`、`6892960`、`3273004` **僅作為測試觀察**：這些 URL 不在硬編碼保底清單，是否出現取決於本輪來源成功發現、下載與解析。
4. 不要在沒有完成 Actions 實際抓取前，宣稱全部來源與品牌已補齊。

## v6.18.1 部署前防護補強

本版以「持續發現新文章」為核心，日常爬取不再依賴逐篇新增固定新聞網址；歷史新聞只留在離線 fixture 作回歸測試。文章來源採多入口互補；任何單一媒體失效，都不應阻止其他來源繼續工作。

### 1. 三層文章發現引擎（沿用 v6.18）

- **直連分類頁／原生 RSS（主力）**：NOWnews 生活分類頁 `/cat/life/` 與生活消費分類頁 `/cat/life/smart-life/` 各最多取 30 篇；新增 TVBS 生活列表（最多 30 篇）；新增蘋果仁原生 RSS `https://applealmond.com/feed`；保留 85°C 與路易莎官方消息頁。
- **Google News RSS（補充廣度）**：保留近 30 天逐媒體／品牌查詢，新增 TVBS 與 ETtoday 查詢。Google News RSS 回傳的文章網址先透過 `googlenewsdecoder` 批次解碼（穩定版 0.2.x）；若解碼失敗，再嘗試 HTTP redirect。仍停留在 Google 網域的網址會記錄並跳過，不把空殼頁誤當成媒體正文。
- **有效舊優惠延續（資料底線）**：`curated_deals()` 不再重灌已過期的硬編碼短期促銷；舊 `deals.json` 中尚未過期且資料合理的優惠會延續，避免新聞列表下架或本輪來源失敗造成長期優惠消失。最近 3 天的文章每輪重新掃描，以捕捉同 URL 更新；超過 3 天且已有未過期優惠紀錄的文章 URL 則跳過重抓。

### 2. v6.18 已修正的解析 Bug

- **7-11 日期誤判**：無年份日期只接受 `11/11` 或 `11月11日`；連字號日期只允許在有年份的日期格式，例如 `2026-11-12`。因此 `date_context("7-11 濃萃美式買2送2")` 應回傳 `(None, None, "")`。
- **跨品牌重複行被刪除**：正文清洗不再做全域文字去重，只刪除連續相鄰的重複行。不同品牌段落中即使出現完全相同的優惠短句，也會保留到品牌／通路作用域解析階段。
- **分類頁抓取深度**：NOWnews 由 15 篇提高到 30 篇，新增 TVBS 生活分類頁；分類頁候選網址必須是媒體原站直連。

### 3. v6.18.1 Google News 解碼超時防護

- `requirements.txt` 已明確包含 `googlenewsdecoder>=0.2.2,<1.0`，GitHub Actions 會透過 `pip install -r requirements.txt` 安裝。
- 先以標題優惠關鍵字篩選，再只處理近 30 天文章；每個 RSS 查詢最多解碼 8 篇，單次 Actions 執行全域最多解碼 40 篇。
- `scrape_report` 會記錄 `google_news_decode_budget_total` 與 `google_news_decode_budget_remaining`，可確認解碼預算使用情況。
- 這個上限是防止大量解碼拖慢工作流程，不代表每個查詢的候選文章都會全部解碼；直連分類頁及原生 RSS 仍是主要來源。

### 4. Google News URL 解碼注意事項

`googlenewsdecoder` 是 Google News 跳轉網址解碼的輔助依賴，不代表所有 Google News 文章都一定可解碼。Google 可能調整格式、部分文章可能受地區或來源限制。每次執行會在日誌記錄解碼結果；解碼失敗會跳過該筆，並由直連分類頁／原生 RSS 入口補足。不要把 Google RSS 的 HTTP 200 當成文章正文抓取成功。

### 5.1 v6.18.1 部署前檢查結果

- `requirements.txt` 已包含 `googlenewsdecoder>=0.2.2,<1.0`。
- Google News RSS 先以優惠相關標題及近 30 天發布日期篩選；每個查詢最多解碼 8 篇，單次執行全域最多 40 篇。
- 更新流程先比較 `deals.json`；沒有檔案差異時會略過 commit/push 並正常結束。
- ZIP 不包含 `__pycache__`、`.pyc`、`.DS_Store` 或編號副本檔。
- 本機離線回歸測試：150 項通過。此結果不等於 GitHub Actions 已完成線上抓取；首次上線仍須手動執行 Workflow 驗證來源連線。

### 5. 安裝與本機測試

```bash
python -m pip install -r requirements.txt
python -m py_compile scraper.py tools/probe_official_sources.py
python -m unittest discover -v
python -m json.tool deals.json > /dev/null
```

測試為離線回歸測試，不會連線抓取即時新聞。

### 6. GitHub Actions 部署

- `.github/workflows/update-coffee-deals.yml`：每 6 小時執行一次（台灣時間約 02:00、08:00、14:00、20:00），也可手動觸發。先跑完整離線測試，再執行爬蟲；只有 `deals.json` 有實際差異時才建立 commit 並推送，沒有新資料時會正常結束，不會因為無變更而失敗。
- `.github/workflows/probe-official-sources.yml`：每週獨立探測官方來源，不執行主爬蟲。
- GitHub repository 的 **Settings → Actions → General → Workflow permissions** 請選 **Read and write permissions**。Workflow 本身也已設定 `permissions: contents: write`。
- 若舊 repository 有其他定時更新 `deals.json` 的 workflow，請停用重複排程，避免同時 push。不要刪除與本專案無關的 workflow。
- 保留 `.github/`、`tools/`、`tests/`、`tests/fixtures/`、`reports/` 目錄。`reports/.gitkeep` 用來讓 Git 保留空目錄。

### 7. 每次執行後看哪裡

請查看 `deals.json` 的 `scrape_report`：

- `listing_discovery.nownews`、`listing_discovery.tvbs`：分類頁是否成功、找到幾篇。
- `native_rss_discovery.蘋果仁`：原生 RSS 是否成功、找到幾篇。
- `source_rss_discovery`：各 Google News 查詢成功率與發現篇數。
- `articles_fetched_successfully` 與 `articles_failed_or_low_content`：候選文章真正抓取正文的成功／失敗數；`articles_skipped_known_stale`：超過 3 天且已有未過期優惠紀錄、因此跳過的舊文章數。
- `google_news_decode_budget_total`／`google_news_decode_budget_remaining`：確認單次解碼預算及剩餘額度。
- 日誌中的 `Google News RSS filtered`、`Google News URL decode failed` 或 `unresolved Google News link`：分辨標題篩選、解碼與跳轉失敗。

### 8. 重要限制

這是多來源盡力發現，不可能保證抓到全網每一篇新聞。分類頁可能改版、網站可能回傳 403/429、原生 RSS 可能延遲或不收錄部分文章、Google News 解碼也可能因 Google 格式改變而失效。請以 `scrape_report` 判斷每個來源的實際結果，不要只看 Workflow 顯示綠色就認定每篇文章都已抓到。

`deals.json` 隨 ZIP 附帶的是上一輪資料快照；上傳新版後，請在 GitHub Actions 手動執行一次 **Update coffee deals**，成功提交新的 `deals.json` 後，GitHub Pages 才會顯示新一輪結果。


## v6.20：審慎加入 HTTP 備援與標題雜訊過濾

- 預設仍使用 `requests`，不需要安裝 Scrapling，原有解析與測試全部保留。
- 若從 GitHub Actions 的 `scrape_report` 確認 Cosmopolitan、ETtoday、TVBS 的原文因 HTTP 403 無法取得，可以在 Repository → Settings → Secrets and variables → Actions → **Variables** 設定 `COFFEE_SCRAPLING_FALLBACK=1`。此時 workflow 才會安裝 `requirements-scrapling-optional.txt`，並僅在上述白名單媒體回傳 403 時以 Scrapling HTTP Fetcher 嘗試一次（每次執行最多 8 次）。**不需要下載無頭瀏覽器**；但 HTTP 備援不保證通過 403 或 JS 驗證，請遵守目標網站的存取規定。
- 不要使用 `pip install scrapling` 取代依賴檔：其基本安裝不包含 fetcher 依賴。本專案的可選依賴是 `scrapling[fetchers]`。
- `is_unsupported_title_only_candidate` 僅拒絕「日期皆空、無正文 details/schedule、新聞標題與 offer 實質相同」的媒體候選卡，不會刪掉有明確商品優惠或官方長期卡的 verify 記錄。**不是把全部 91 筆待確認資料一次刪除。** 報表新增 `title_only_undated_candidates_rejected` 與 `undated_verify_records_retained`，可量化效果。
- 首次上線請先以預設模式執行一次；檢查 `articles_failed_or_low_content`、`scrapling_fallback_attempts`、`title_only_undated_candidates_rejected`，再決定是否開啟 HTTP 備援。
