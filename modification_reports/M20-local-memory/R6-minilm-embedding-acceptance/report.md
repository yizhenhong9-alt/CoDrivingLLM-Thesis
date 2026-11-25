# M20-R6：固定 MiniLM 下載與真實向量驗收

## 狀態

2026-11-25：本地來源核驗測試 6/6 通過；Spark 真實模型驗收待使用者手動執行。
前置證據：step5 console 顯示 R5 CPU runtime PASS、Chroma 14/14 通過、exit 0，結果目錄 `M20-R5-minilm-runtime-jhL8nq`。這只代表套件可用，尚未載入 MiniLM。

## 變更編號

- R6-01：[驗收程式](../../../../validation/accept_minilm_embedding.py)：限制 Spark ARM64 與第三個 memory 環境，逐項比對 R5 已驗收套件版本，不安裝套件。
- R6-02：由 Hugging Face 固定 commit API 取得允許清單的檔案大小與來源 hash；LFS 使用 SHA256，普通 Git blob 使用含標頭的 SHA1。必須有 safetensors，不回退 main 或 pickle。新檔先驗證，再以不覆寫既有檔案的 hard link 發布；既有檔案不符即停止。下載權重只在 Spark 執行。
- R6-03：核驗 hidden size、BERT 類型、256 tokens 與 mean pooling 設定；離線 CPU 編碼原 R2 的兩筆案例。驗證 384 維、L2 norm、batch/single 一致性、超長拒絕、Chroma top-2、對應 top-1、metadata 與重開後邏輯快照。
- R6-04：[操作腳本](../../../../validation/accept_minilm_embedding.sh)：一次完成下載和離線測試；記錄資源、Git commit、來源 metadata/hash、模型冷載入與五次暖機後「編碼加檢索」延遲。所有模型、快取與測試 DB 限 `/home/nclab/Yizhen`。
- R6-05：[離線測試](../../../../validation/check_minilm_acceptance.py)：revision 不符、缺權重、allowlist、LFS、錯誤大小、兩種 hash 與同大小損毀等六個測試案例。

## 測試與界限

Windows 執行 `validation/check_minilm_acceptance.py`：6 tests、OK；沒有網路請求、模型載入或 ML 套件匯入。Shell 腳本本地未實跑，模型 API 與固定 commit 檔案是否齊全須以 Spark 結果確認；缺檔或 metadata 不符會停止。

Spark 操作：在 repo 根目錄執行 `bash validation/accept_minilm_embedding.sh`。回傳整段 console，尤其 exit code、結果目錄與 acceptance.json。失敗時保留結果，不自行變更模型 revision。下載需要外網，但不呼叫雲端 embedding；情境文字不傳上網。檔案核驗信任 HTTPS 取得的官方 Hub metadata，並非獨立簽章驗證。

驗收只使用隔離的兩筆原始模板測試資料，不寫正式訓練記憶。重開測試是同一程序，R3 已另做 Chroma 跨程序持久化測試；R6 未重新宣稱真實向量跨程序驗收。相同的 empty-conflict 文字無法辨別不同歷史動作；兩筆 top-1 通過不能證明全部交通語意相關或安全改善。

正式 memory off、CAV prompt、create_memory(on) 狀態、安全公式、速度處理均未改。沒有 Qwen 重部署、20 seeds 重跑或 Windows 模型下載。此關通過後仍需 memory 服務跨環境串接及最小 memory-on 端到端驗收；尚未開啟正式實驗。
