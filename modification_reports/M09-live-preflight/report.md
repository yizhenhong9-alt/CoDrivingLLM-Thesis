# M09：真實 API 前的只讀資源與停服證據檢查

日期：2026-11-23。

## 前置結果與問題

M07 的兩版 fixture 與 M08 的 10 筆 token 計數均已由使用者在 Spark 完成。接下來要取得真實 Qwen 回覆，但目前本地沒有 Step8J-R1 原始啟動、停服程式及 launch-config.json，只有交接摘要。交接記錄成功回覆後，同時對程序群組送 SIGTERM 出現 EngineDeadError/semaphore 警告；不能將其視為正常停服已驗證。

歷史 available 約 92 GiB 不是當下資源，也不保證能重啟模型。不重做 R4/8F、下載或權重逐檔核驗。

## 修改內容

新增 [inspect_qwen_runtime.py](../../validation/inspect_qwen_runtime.py)。以標準函式庫讀取 /proc/meminfo、負載、個人目錄所在磁碟容量、套件 metadata 和已安裝 vLLM 的停服相關 source excerpts；執行只讀的 nvidia-smi、ss、ps。ps 僅記錄 PID/PPID/PGID/comm，不讀程序環境變數或完整參數。

讀取既有 step8J-R1-api-smoke-d41rak3z 中 launch-config.json、result.json，以及 run-smoke.py 中啟停相關片段。缺檔會記錄，不假裝已取得。這是收集既有證據，不是重跑原測試。

除新建報告目錄及 JSON 外不寫入其他檔案；不匯入 torch/vllm、不跑 CLI --help、不建立 CUDA 計算、不連線模型 API、不安裝/下載、不發 signal、不改任何人的服務、Docker、驅動或全域設定。仍會有少量共享 CPU/RAM/I/O，以及 nvidia-smi 的驅動狀態查詢成本。

status=snapshot_collected 僅代表資料收集完成，不能解讀為可啟動或已預留資源。incomplete 表示部分資料無法取得，保留結果回傳。

## 官方 source 研究與候選停服方式

查閱版本固定的官方 [v0.34.0 launcher.py](https://github.com/vllm-project/vllm/blob/v0.34.0/vllm/entrypoints/launchers/launcher.py) 與 [serve.py](https://github.com/vllm-project/vllm/blob/v0.34.0/vllm/entrypoints/cli/serve.py)，確認有 SIGINT/SIGTERM handler 與 shutdown_timeout 路徑。這是上游程式資訊，不代替已安裝檔案或本機測試證據。

候選方式是停止送入請求、等待當次 API 呼叫結束，再只通知本次已記錄且確認身分的 API 主程序，由它處理子程序退出。不能使用 pkill、killall、群組同步 SIGTERM、或依共用 nclab 帳號猜測程序歸屬。是否採用、使用哪個 timeout 及精確啟停命令，要先比對已安裝 source 與原成功設定。

若正常等待後仍殘留程序，先保存 PID/父子關係/埠/日誌，不自動 SIGKILL。本輪不提供或執行模型啟停命令，不宣稱修好了 EngineDeadError 或 semaphore。

## 本地驗證

[check_runtime_inspection.py](../../validation/check_runtime_inspection.py) 使用 fake source 與 subprocess test double；檢查記憶體解析、source 行號及 SHA256、缺系統指令記錄，以及沒有載入 torch/vllm。結果見 [test-results.txt](./test-results.txt)。不把這些測試當成 Spark 資源或停服測試。

## Spark 待執行

同步本輪版本、確認遠端工作樹乾淨後，用既有推論 interpreter 執行：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/inspect_qwen_runtime.py --output-dir /home/nclab/Yizhen/runs/M09-preflight
```

回傳 console 與 result.json。所有遠端新增輸出限 /home/nclab/Yizhen。報告是當時快照，之後若延遲或共享負載改變，啟動前仍須重查。

## 尚未驗證與下一階段

待取得 Spark source 與既有 Step8J-R1 證據後，整理精確啟停指令與程序身分記錄。使用已下載的官方 Qwen/Qwen3-30B-A3B-Instruct-2507-FP8、revision 5a5a776300a41aaa681dd7ff0106608ef2bc90db。首次真實交通回覆先使用 live 而不加 --apply-step，通過後再安排真正單步；不是重做 1+1 或合成 GPU 測試。

記憶模式維持 off，安全公式、優先權與 5 m/s 限制保留。實際協商回覆可能改變後續 action 提示長度，M08 fixture 計數仍不保證所有真實請求符合 2048。

## Spark 已取得結果與核對

使用者提供 20261123T063318Z-d85e982b/result.json，本地已讀取資源、歷史 launch-config/result、run-smoke.py 摘錄及全部 installed source excerpts，非直接登入 Spark。

- 當時 MemAvailable 為 92.49 GiB；18080 的 ss 結果只有表頭，無監聽程序。
- vLLM 0.34.0、Python 3.12.3、PyTorch 2.14.0+cu130、Transformers 5.22.2；warnings 與 forbidden_modules_imported 均為空。
- 取得 Step8J-R1 原始設定，確認 served-model-name 使用不含 Qwen/ 的短名稱；目前 client 要求完整名稱。M10 將服務別名統一為完整名稱，保留權重及主要執行參數。
- 已安裝 arg_utils.py 明確定義 --shutdown-timeout，預設 0，help 為 0=abort、>0=wait；launcher.py 註冊 SIGINT/SIGTERM 並讀取 shutdown_timeout。此為已安裝 source 證據，不只上游資訊。
- 原 run-smoke.py 實際使用 killpg 同步發 SIGTERM，逾時可 SIGKILL；M10 不沿用此方式。

保存必要來源與 SHA256 的 [核對摘錄](./spark-review.json)；完整原檔仍在使用者提供的 runs/M09-preflight/20261123T063318Z-d85e982b。未重驗權重大小或 SHA256；停服改善尚未實測。92.49 GiB 僅為當時快照。
