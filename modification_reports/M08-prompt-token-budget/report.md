# M08：新版提示 token 計數與 Python 環境分工

日期：2026-11-23。

## 修改前

原有 token 數字來自舊提示，不適用於 M05 已調整的提示。M07 已在 Spark Python 3.8.20 完成 strict/legacy fixture，提供兩份各 5 次呼叫的 messages，可以不重跑模擬而直接量測。沒有以歷史 2048 設定保證足夠。

## 修改內容

新增 [count_qwen_prompt_tokens.py](../../validation/count_qwen_prompt_tokens.py)，在既有推論環境讀取本地 tokenizer，先渲染 chat template 與 generation prefix，再以 add_special_tokens=False 編碼，避免重複加特殊符號。每次記錄輸入長度、預留輸出、剩餘空間、是否符合指定上限、提示檔 SHA256 與 template SHA256。

CLI 僅供 Spark 執行，所有讀取與輸出路徑限制於 /home/nclab/Yizhen。local_files_only=True、trust_remote_code=False，關閉網路與 CUDA 裝置。沒有 AutoModel、權重載入、模型服務啟動或下載步驟。程式預期 revision 為 5a5a776300a41aaa681dd7ff0106608ef2bc90db，但不重新核驗權重；原權重核驗仍依交接證據。

## 修改後本地測試

Windows Python 3.13.13 使用 fake tokenizer，4 項通過，見 [test-results.txt](./test-results.txt)。確認 chat template/generation prefix 編碼流程、輸出預算加總、超額判定、拒絕錯誤模型或失敗的 fixture，以及無效 messages。

本地沒有載入真實 tokenizer 或模型，也沒有安裝套件。真實 token 數值已由使用者在 Spark 執行並提供，見下方結果。

## Spark 實測結果：已完成

來源為使用者提供的 20261123T062124Z-e24e933f/result.json；本地已完整讀取並核對全部 10 筆輸入加預算、剩餘空間與 fits 計算。保存 [原始結果副本](./spark-result-20261123T062124Z-e24e933f.json)。這是對提供檔案的核對，不是遠端重新執行或重新核驗權重。

Python 3.12.3、Transformers 5.22.2，結果 status=measured、all_fit=true。tokenizer 類別回報 Qwen2Tokenizer；此為 tokenizer 實作類別名稱，單憑類別名不能判定載入了另一個模型。記錄的模型目錄與預期模型一致，權重 revision 仍依交接證據。

| 提示 | strict 輸入 | legacy 輸入 |
|---|---:|---:|
| negotiation | 453 | 353 |
| action 車 3 | 977 | 967 |
| action 車 4 | 872 | 862 |
| action 車 5 | 986 | 976 |
| action 車 6 | 813 | 803 |

每筆預留輸出 256、候選上下文上限 2048。最大輸入為 strict 車 5 的 986，加輸出後 1242，剩 806；所有 10 筆均符合此次預算。這些是各自獨立 API 請求，不需把 5 次輸入相加後與 2048 比較。

此結果支持使用 2048 作為這批提示初次真實回覆測試的候選設定，不保證任意場景、真實協商內容或回覆長度都足夠。token 計數未產生模型回答；尚無真實解析率、延遲或碰撞率結果。無需重跑本次計數。

## 為什麼有不同 Python 版本

| 環境 | Python | 工作 |
|---|---|---|
| Windows 本地目前可用 interpreter | 3.13.13 | 編輯與不依賴模擬器的測試；不安裝/載入 Qwen |
| Spark codriving-sim-py38 | 3.8.20，M07 結果已確認 | 原交通模擬、提示生成、parser、車號與動作檢查 |
| Spark qwen-vllm034-py312 | 3.12，依部署交接 | 新版 vLLM/Transformers 推論，以及本次 tokenizer 計數 |

這不是所有程式同時混用三個 Python。每個程序只能使用自己選定的 interpreter 和套件。舊模擬專案含 gym==0.15.3、pandas==1.3.5 等既有依賴；保留已驗證的 3.8 基線可避免把環境升級問題混入模型研究。推論使用另一套較新的套件環境。這不表示模擬器永遠只能用 3.8；未來若升級須獨立驗證。

正式執行時，3.8 程式傳送 HTTP/JSON，3.12 服務回傳文字，兩個程序不直接共享 Python 記憶體或互相 import 套件，因此不要求版本相同。但仍需檢查 API 格式、回覆內容和逾時等行為，不能說分環境就完全沒有相容性問題。不要把模擬 requirements.txt 安裝到推論環境，也不要用 pip --user 混裝。

## Spark 已執行指令（留存，不需重跑）

先同步包含 M08 的 Git 版本；不用啟動模型。指定既有的 3.12 推論 interpreter：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/count_qwen_prompt_tokens.py \
  --model-dir /home/nclab/Yizhen/models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4 \
  --fixtures /home/nclab/Yizhen/runs/M07-offline/20261123T044039Z-baa96999/strict/20261123T044039Z-d08cd9b4.json /home/nclab/Yizhen/runs/M07-offline/20261123T044039Z-baa96999/legacy/20261123T044041Z-f43a8225.json \
  --output-dir /home/nclab/Yizhen/runs/M08-prompt-tokens \
  --context-limit 2048 --output-tokens 256
```

預期 status=measured；如果 context_exceeded，退出碼 2 表示指定預算放不下，不是下載或套件故障。failed 表示其他錯誤，保留 result.json，不自行安裝或換模型。

## 判讀限制與後續

只量測 seed 0、memory off 的人工協商結果提示。真實協商改變內容、其他 seed/車數/memory on 時須再評估。256 是本次預留輸出預算，不能保證回答完整。2048 是用於比較既有健檢設定的候選上限，不能提前稱為正式實驗設定。

本次不啟動 Qwen。真實回覆前還需確認共享資源與正常停服流程；既有 EngineDeadError/semaphore 事項仍保留，不宣稱已修好。
