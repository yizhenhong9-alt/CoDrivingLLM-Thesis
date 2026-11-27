# M24-R7：方向1，原860庫保留、副本恢復800、單次seed3重試

2026-11-27。使用者明確選擇方向1：「排除seed3所產出的memory，重跑seed3」。授權範圍為準備恢復與一次seed3重試，不自動接4–19；Spark操作均由使用者手動。未採方向2，prompt／strict完整pair檢查／安全公式／速度／模型服務參數不變。

## 鎖定來源與恢復邊界

- 原run：`/home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-PvMXov`。
- 原commit4ab0865081a2b686613a9b29abc4f50d6cfc05a4；seed1、2碰撞結果與seed3原失敗全部保留。
- 原860筆snapshot：`c87691df4faa150eede66d0fde4b30a7b5e28fc6d7ca74a58e3ea3b8f88f3c94`。
- 目標800筆snapshot：`e3b4429eef5e0508784dee80821bed5d8996824ecbd1aa5f243210faac34c787`。
- 來源260個實際run證據檔SHA256固定於 [R7-seed3-retry-source-contract.json](./R7-seed3-retry-source-contract.json)。來源run本來沒有collector產生的SOURCE.txt／SHA256SUMS，故不在來源run要求它們；新loader先核對260個固定hash，再重跑R6資料鏈審查，而非跳過來源驗證。原R6 CLI仍預設驗證匯出SHA256SUMS。

## 副本恢復：不在原庫開Chroma

[recover_m24_seed3.py](../../validation/recover_m24_seed3.py) 驗證完整原始證據、800個保留ID與60個排除ID、未改的決策／prompt／服務程式。原庫僅做檔案hash與copy；有writer.lock即拒絕，不自動刪lock。

目的必須是/home/nclab/Yizhen內的全新、不與來源互相包含的目錄。copy完成先要求全部檔案hash相等；只在副本開Chroma，核對860筆的count、包含向量的snapshot、全部ID／text／metadata。通過後僅刪除明確60個ID，不更新metadata、不add、不重算embedding。刪除後再核對完整800筆與目標snapshot，來源前後檔案hash相同才ready。

保留原860庫及所有失敗檔；新run的prior-attempt複製白名單證據，不複製DB進匯出檔。原seed0的test_only=true不改，seed1／2紀錄亦不改；重試新紀錄維持test_only=false。準備收據為seed3-recovery.json，記錄全部60個排除ID、來源hash、兩個邊界、prompt_changed=false／strict_changed=false。

logical snapshot相同不代表刪除後HNSW實體索引位元級還原，也不保證tie邊界或模型回答完全相同；不能把方向1稱為已修復漏答原因。

## 單次重試入口

[run_m24_seed3_retry.py](../../validation/run_m24_seed3_retry.py) 只接受ready的800筆副本，重查原860庫未變、來源證據與決策程式未變，並要求Spark乾淨checkout。以x模式建立retry-started.json後啟服務；同一副本已有marker或retry-result即拒絕，不覆蓋、不自動再試。

使用原manager、原seed3、strict、memory on、300步／3600秒。起始服務count必須800且snapshot精確匹配；成功時重跑原validate_episode、M24身份與動作順序、config／model／parser、rolling corpus及正常停服驗收。自然碰撞仍是有效結果，不等於技術失敗；不要求挑到無碰撞。失敗保留部分寫入與原始回覆。結果記seed=3、attempt=2，不覆蓋attempt1。

**無論重試成功或失敗，均不啟動seed4，也不進一步自動重試。** 原transport仍temperature=0；重跑可能再次漏答，不能承諾換一次執行就會成功。禁止反覆新建副本挑成功結果。

## 本地測試與目前狀態

- check_m24_seed3_retry：11項PASS，含精確刪60筆／保留800不改、錯count／snapshot／ID／text／metadata／shape／readonly拒絕、刪除後驗證失敗不宣稱成功、原writer.lock不刪、只開新副本且原bytes不變、source mutation／prompt／strict變更拒絕、失敗只一次並收尾、成功驗證warm corpus後仍停seed3、白名單保留失敗資料不含DB。
- 舊M24 continuation11、memory recovery4、batch3、episode3項PASS，合計32項。
- 真R6匯出資料重新load：800保留／60排除PASS，決策／prompt／strict／服務來源對原seed0無差異PASS。
- Python3.8 AST檢查與兩份shell bash -n通過；新增Python編輯器診斷無錯。

以上是Windows stdlib／替身與真JSON證據驗證，不是Spark真Chroma還原或重試成功。尚未對Spark做任何操作。

## 使用者手動執行順序

1. 更新qwen-local後執行 [prepare_m24_seed3_retry.sh](../../validation/prepare_m24_seed3_retry.sh)。此步只建恢復副本，不啟Qwen、traffic或embedding模型；所有新檔/cache在/home/nclab/Yizhen。
2. 回傳結尾Review archive所列tar.gz，檢查Spark source_unchanged／800 snapshot／60排除清單與ready狀態。
3. 副本通過後，以回傳的實際新run路徑使用 [retry_m24_seed3.sh](../../validation/retry_m24_seed3.sh)，由使用者以nohup啟動一次。此處不預填未知run尾碼；待收據給出後提供確切可貼指令。

共用Linux帳密不代表擁有同帳號其他人的資源。新工具不掃描／終止他人程序、不清swap／cache、不修改他人環境。既有manager只收尾自己啟動並追蹤的服務；遇既有服務／資源不足依原guard停止。原作者副本未修改；R4既存刪除未restore亦不納入commit。
