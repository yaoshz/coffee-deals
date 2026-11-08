# 省咖啡｜優惠雷達 v6.17

## v6.17 核心重構

- **Span-Based Offer Parser**：先遮蔽日期區間，再依促銷語法優先級擷取互不重疊的字元區間；避免「第 2 杯 11 元」被誤讀為「2 杯 11 元」。
- **中文數字**：支援零至九、十、十一、十六、十九、二十一、二十五、百／千等常見促銷數字。
- **Hybrid Section Splitter**：保留 H2/H3/H4、段落、清單及粗體資訊；以明確品牌前綴切換品牌，遇到多品牌導言時重置品牌上下文，不讓前言污染後續優惠。
- **Brand Scope + Channel Scope**：同時維護品牌與通路；`channel_scope` 成為 `deals.json` 一級欄位，允許值為 `app`、`store`、`delivery`、`unknown`。沒有明確證據時預設 `unknown`，不猜測門市。
- **Fair-Share Round Robin**：同一 URL 全域只排程一次；依發布日期排序後按品牌輪替，並限制單一來源最多 25 篇，總量仍受 `MAX_ARTICLES=160` 控制。
- **離線 HTML fixtures**：四篇指定 NOWnews／Yahoo 文章使用靜態 HTML 測試素材，單元測試不連線新聞網站。
- **GitHub Actions**：新增每日台灣時間 07:30 更新流程，先跑離線測試再執行爬蟲並提交 `deals.json`；另有獨立官方來源探測 workflow。
- **官方來源獨立探測**：新增 `tools/probe_official_sources.py` 與獨立 GitHub Actions workflow。探測 7-ELEVEN、全家官方首頁及最多 8 個可發現的站內活動／咖啡候選頁，記錄 HTTP 狀態、回應大小、文字長度、關鍵字與候選連結；403／429 僅記錄，不繞過網站防護，也不阻擋主爬蟲。
- **前端通路標籤**：卡片可顯示 APP／線上寄杯、門市、外送；`unknown` 不顯示錯誤的門市標籤。

## 驗收

本次版本離線回歸測試共 **128 項，全部通過**。測試涵蓋既有去重案例、4 篇靜態新聞 fixture、Span 衝突、中文數字、品牌／通路作用域、公平配額與官方探測 403 模擬。

```bash
python -m unittest -v test_scraper_dedup.py
python -m py_compile scraper.py tools/probe_official_sources.py
python -m json.tool deals.json > /dev/null
python tools/probe_official_sources.py --output official_source_probe.json
```

官方探測是獨立診斷，不屬於主爬蟲必要步驟。GitHub Actions Runner 可能因 IP／WAF 政策得到 403 或 429；這只代表該次 Runner 的可讀性，不代表官網永遠不可用。可透過 `OFFICIAL_PROBE_URLS` 環境變數，以分號加入已確認的官方活動頁網址。

## GitHub Actions 部署（首次上傳前必讀）

### 1. 確認 GitHub Actions 寫入權限

本專案的 `.github/workflows/update-coffee-deals.yml` 已在 YAML 中設定：

```yaml
permissions:
  contents: write
```

這是讓該 workflow 的 `GITHUB_TOKEN` 可以提交更新後 `deals.json` 的必要設定。上傳後仍請到 GitHub repository：

**Settings → Actions → General → Workflow permissions**

選擇 **Read and write permissions**，再按 **Save**。若組織政策限制 workflow 權限，仍須由有權限的管理者確認。

### 2. 檢查舊的排程 workflow，避免重複執行

上傳前，先檢查 repository 的 `.github/workflows/` 目錄。如果原本已有其他會定時執行 `scraper.py`、更新 `deals.json` 或推送相同資料的 workflow（例如 `main.yml`、`scraper.yml`、`update.yml`），請停用或移除重複的排程，避免兩個流程同時提交而發生 push conflict。

**不要刪除所有舊 workflow。** 只處理確認與本專案更新工作重複的流程；其他用途的 Actions 可以保留。完成後，本專案的主要排程檔為：

- `.github/workflows/update-coffee-deals.yml`：每日台灣時間 07:30 更新優惠。
- `.github/workflows/probe-official-sources.yml`：每週獨立探測官方來源，不會執行主爬蟲或提交 `deals.json`。

主更新 workflow 已設定 `concurrency`，可避免同一個 workflow 群組的更新工作重疊；但它不能取代停用其他重複 workflow。

### 3. 上傳整個專案

請保留專案中的 `.github/`、`tests/`、`tools/` 與 `reports/` 目錄。`reports/.gitkeep` 是用來讓 Git 保留目前沒有報告檔案的空目錄，不是爬蟲執行的必要程式。

第一次上傳後，到 **Actions** 頁面確認 workflow 有出現。可以先手動執行 `Update coffee deals`，檢查測試、爬蟲及 `deals.json` 自動提交是否成功。

## 主爬蟲執行

```bash
pip install -r requirements.txt
python scraper.py
```

主爬蟲仍使用新聞 RSS 與媒體列表發現文章；官方來源探測不會被主爬蟲呼叫。請檢查 `deals.json` 的 `scrape_report`，並回原文核對日期、通路、限量與會員條件。

## 重要限制

- 本版交付的 `deals.json` 是 2026-11-08 的離線正規化快照，不代表已在本次環境完成全站即時抓取。
- Google News RSS 是文章發現補充來源，不是官方 API，也不保證完整或即時。
- 本機與 GitHub Actions 對同一官網可能得到不同 HTTP 結果；不要以單次 403 推斷網站永久不可用。
- 文章導言或同一段落出現多品牌時，採保守策略不繼承品牌；無法確定品牌／通路時保留 `unknown`，避免錯誤優惠卡。
