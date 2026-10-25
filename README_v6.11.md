# 省咖啡｜優惠雷達 v6.11

## 本版重點

- **語意化活動欄位**：`start_date`／`end_date` 用來判斷優惠日期狀態；`date_text` 只呈現日曆期間；新增 `schedule_note` 儲存週期日與限定時間，不參與 `active`／`expired` 計算。
- **向後相容**：舊 `deals.json` 即使沒有 `schedule_note`，也會從 `date_text` 的分號尾註、優惠文案或補充說明回填；前端亦保留舊快照 fallback。
- **防止時段上下文外洩**：時段上下文綁定店家，而且只套用到下一筆合格優惠。店家切換、跨店彙整、`另外／四大超商` 等摘要轉折、APP／隨買跨店取／整買零取／LINE 禮物／電子票券等通路切換，都會清除舊時段；若新段落有自己的時段，才重新建立。
- **各品牌週期資訊標準化**：星巴克每週一 uniopen 買一送一、每週二指定飲料糕點優惠；全家週三咖啡日；小北百貨週三會員日；萊爾富 Happy Hour 每週六、日 10:00–14:00，都以 `schedule_note` 獨立呈現。
- **三語顯示**：保留繁體中文、英文、泰文切換，並顯示「限定時段」標籤；舊快照可從 `date_text` 回退擷取。
- **修正安全寫檔**：`safe_write()` 透過暫存檔與原子替換寫入，避免重複輸出 JSON 文件。
- **保持 SSOT**：後端完成品牌及優惠排序，前端不重做一套優惠權重排序。

## v6.11 快照資料

- `deals.json`：**92 筆**離線清理資料。
- 狀態統計：有效 **72**、尚未開始 **0**、待確認 **17**、已過期 **3**。
- 萊爾富 29 元 Happy Hour 卡片：`date_text = 10/14～11/10`；`schedule_note = Happy Hour｜每週六、日 10:00–14:00`。
- 資料清理後重跑去重仍為 92 筆。所有優惠都具備 `schedule_note` 欄位（沒有週期限制時為空字串）。
- **這是離線修正快照，不是全新即時抓取**。`updated_at` 保留來源抓取時間，`corrected_at` 記錄本次離線修正時間。

## 部署

將 `scraper.py`、`deals.json`、`index.html`、`requirements.txt` 和 `test_scraper_dedup.py` 覆蓋到 GitHub 專案。保留原有 `.github/workflows/update-coffee-deals.yml`。

建議先在本機或 CI 執行測試，再手動觸發 GitHub Actions。請確認 Actions 成功且最新 `deals.json` 中 `schedule_note` 不再只留在 `date_text` 尾註。

## 測試

```bash
python -m unittest -v test_scraper_dedup.py
python -m py_compile scraper.py
python -m json.tool deals.json > /dev/null
```
