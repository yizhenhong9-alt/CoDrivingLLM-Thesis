# M20-R6：固定 MiniLM 下載與真實向量驗收

## R6-06 修正：固定版本的權重格式（2026-11-25）

使用者 Spark 執行 `44abed3` 於 `M20-R6-minilm-acceptance-T2QUMs` 失敗，exit 1、`KeyError: model.safetensors`。失敗在 API 清單選取，尚未下載權重或執行 embedding；當時 available RAM 92 GiB、磁碟 2.3 TiB，不是資源不足。

原因是開發時沒有先查證固定 commit 的實際檔案，將新版本的 safetensors 檔名套用到舊 commit。[官方固定 commit 清單](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/717413c64de70e37b55cf53c9cdff0e2d331fac3)實際提供 `pytorch_model.bin`，沒有 `model.safetensors`。以下原始 R6-02「必須有 safetensors、不讀 bin」的設計由此節明確取代；模型 revision 不變。

- R6-06a：下載 allowlist 改為該 commit 的 `pytorch_model.bin`。來源 metadata 先落盤，再驗證必需檔案；缺檔改回報具體 ValueError，保留診斷證據。
- R6-06b：hash 核驗後，在 Spark 使用 `torch.load(map_location='cpu', weights_only=True)` 讀取非空的純 tensor state dict；不開啟 unrestricted pickle 或 remote code，不放寬 allowlist。再以 safetensors 儲存衍生檔，記錄原始與衍生 SHA256、tensor 數與 torch 版本至 conversion.json。既有衍生檔必須與此次轉換相符，否則停止、不覆寫。[PyTorch 2.9 說明](https://docs.pytorch.org/docs/2.9/notes/serialization.html)指出 weights_only 限制可反序列化的型別；這不代表所有不受信任來源皆無風險，仍須先驗證官方固定版本來源。
- R6-06c：既有 encoder 維持 `use_safetensors=True`，384 維、pooling、256 tokens、Chroma 與 memory off 均不改。檔案格式轉換不改模型參數值，不更新 embedding 模型。第三環境既有 torch 與 safetensors 足夠，不安裝新套件。

修正本地測試：來源與轉換測試 11/11 通過；包括舊版無 safetensors 清單、限定 weights_only/CPU 呼叫、非 tensor 拒絕、hash 不符時不載入、既有衍生檔不覆寫。轉換採替身，不在 Windows 匯入真實 torch 或載入模型。既有 local-memory 回歸 16 項：15 通過、1 因 Windows symlink 權限略過。Spark 真實權重轉換與編碼尚待使用者重跑同一腳本，不宣稱已通過。

原失敗結果保留，腳本每次建立新的 run 目錄；不需刪除任何目錄或重裝環境。

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
