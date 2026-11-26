# M23-R1：隔離副本檢索診斷

2026-11-26，新增validation/diagnose_memory_retrieval.py。原401筆庫只做檔案hash與copy，不由Chroma開啟；writer.lock存在則拒絕、不移除。Chroma只開新個人目錄副本、adapter writable=false，無add／Qwen／模擬器或實驗重跑。

對所有已保存query及stored text加前導newline的變體、空摘要進行CPU MiniLM→raw Chroma query→adapter search探測。保存query hash／長度、階段、數值distance／結果欄長度及固定白名單錯誤訊息，不記錄情境全文或未知exception message。前後核對原檔hash與副本邏輯snapshot／count。Chroma可能改寫副本內部檔案，故不稱實體檔案完全唯讀。

重要限制：失敗車4 query在舊流程prepare失敗前未被保存，本診斷是有限候選探測，不保證精確重現該次HTTP400；若全部PASS，也不能宣稱已修好。僅沿用既有離線模型與環境，不下載或轉換。

本地Windows僅Python3.8 AST語法檢查通過，沒有載入ML／Chroma、未在Spark執行，沒有宣稱完整runtime測試。真診斷由使用者手動。回傳diagnosis.json與console即可，不回傳副本DB／cache。正式memory與安全公式未改。
