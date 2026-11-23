# M05：Qwen 專用單步入口

日期：2026-11-23。正式模型固定為 Qwen/Qwen3-30B-A3B-Instruct-2507-FP8。
指定權重 revision 為 5a5a776300a41aaa681dd7ff0106608ef2bc90db；API model name 檢查本身不能證明後端載入的權重 revision，仍需配合 Spark 啟動設定與既有部署紀錄。

## 修改前

原入口使用原 OpenAI agent、固定多回合、影片及 Excel 輸出；沒有獨立 Qwen 單步控制入口。M01–M03 工具尚未接入。因此不應直接執行原入口來做本次 Qwen 驗證。

## 修改範圍

- [qwen_step.py](../../llm_controller/qwen_step.py)：串接原衝突偵測、原 action prompt_engineer 與安全工具，以及 M01–M04 檢查。
- [qwen_transport.py](../../llm_controller/qwen_transport.py)：僅連線 127.0.0.1 的既有服務，關閉代理及 redirect，核對 /v1/models；不安裝、下載、啟動或載入模型。
- [run_qwen_single_step.py](../../validation/run_qwen_single_step.py)：新增 CLI，預設 fixture，必須明確給輸出資料夾。live 預設仍只驗證回覆；另加 --apply-step 才執行一次 env.step。

原 agent 和兩個 parser function 未修改。M05 使用原 agent 的資料與安全方法，不呼叫其 send_to_chatgpt；載入時以會報錯的 OpenAI stub 防止誤用雲端 SDK。memory 維持 off。

目前 runtime 僅接受 intersection。M02 的 merge/highway 設定不表示 M05 已驗證其他場景。

## Parser 與提示比較方式

--parser legacy 使用原 extract_decision、extract_vehicle_conflicts；--parser strict 使用新版 JSON parser。每份原始回覆均同時交給兩版 parser，保存結果，選定版本通過後再做車號、數量、配對與當下可用動作檢查。legacy 模式不是完全不檢查的作者原始系統。

legacy 協商使用原顯示車號；strict 協商使用 simulation ID。嚴格結果先轉成原工具需要的車號文字，以保留原讓行判斷路徑；若原顯示標籤碰撞則拒絕，不能猜車。

兩種模式的 prompt 輸出格式不同。因 schema 不相容而拒絕不能直接計為 parser 能力差異。M05 重新組合提示，保留原規則與注意事項、移除空 memory 段落與 ChatGPT 身分，路口輸出不再列換道；這是 M05 prompt 版本，並非完全重現作者 prompt。每次保存完整 messages。

安全公式、動作優先權與逐車 5 m/s 截速保留。fixture 即使不 env.step，原 prompt 建構仍可能因截速改變車輛狀態，因此記錄前後車輛快照；不能把不 step 解讀成完全不改物件。

## 修改後本地測試

Windows Python 3.13.13 執行 [check_qwen_single_step.py](../../validation/check_qwen_single_step.py)，12 項通過，見 [console](../M05-test-results.txt)。

| 測試 | 實測結果 |
|---|---|
| strict/legacy fixture、原 parser method body | 兩種流程均產生 (1,1)，不呼叫 env.step |
| fixture 加 apply-step | 拒絕，不推進 |
| 假 live transport + 假環境 | 全部答案通過且已保存後，只 step 一次 |
| 錯車號、協商漏項、逾時、錯執行編號表 | 不 step；保存原始回覆或錯誤；不重試、不自動補 IDLE |
| HTTP request test double | 模型固定為指定 30B、端點固定 loopback |
| finish_reason=length、錯 model 清單 | 拒絕；截斷 API 回覆保留 |
| Python 3.8 grammar | 新入口與核心模組的 AST 語法檢查通過，不等於 Python 3.8 runtime 驗證 |

假 live transport 測試沒有網路或真實模型；假環境測試也不驗證真實動力學。原 parser method body 有執行；完整安全工具、真實 prompt_engineer 與模擬套件仍待下面的 fixture 測試。

## 完整 CLI 試跑失敗紀錄

在同一本地 interpreter 執行 fixture CLI，因 ModuleNotFoundError: No module named 'gym' 於匯入模擬套件時停止，退出碼 1，environment_steps=0。未安裝新套件、未送模型。

證據：[CLI 試跑結果資料夾](../M05-local-cli-attempt/)。此紀錄是執行當時版本快照，後續小幅紀錄欄位調整不回寫歷史檔案。完整 CLI 未通過，不列為整合完成。

## Spark 下一次驗證：僅離線，不啟動模型

需先審查 Git 差異並 commit/push，再由使用者手動 Remote-SSH 核對遠端工作樹並 pull；本輪未操作 Git 同步。不要覆蓋遠端未提交內容。確認要驗證的 commit 後，在既有模擬環境執行：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
export PYTHONDONTWRITEBYTECODE=1
export XDG_CACHE_HOME=/home/nclab/Yizhen/cache
export MPLCONFIGDIR=/home/nclab/Yizhen/cache/matplotlib
export TMPDIR=/home/nclab/Yizhen/tmp
mkdir -p "$XDG_CACHE_HOME" "$MPLCONFIGDIR" "$TMPDIR"
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/check_qwen_single_step.py
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/run_qwen_single_step.py --mode fixture --parser strict --seed 0 --output-dir /home/nclab/Yizhen/runs/M05-fixture-strict
/home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/run_qwen_single_step.py --mode fixture --parser legacy --seed 0 --output-dir /home/nclab/Yizhen/runs/M05-fixture-legacy
```

預期 validated_not_applied、1 次協商加每車 1 次 action、environment_steps 和 actual_environment_steps 均為 0、memory_module_imported=false。fixture 是任意低 ID 先行及 IDLE，不能用它的通過主張交通安全。

真實模型回覆、單步、Python 3.8 結果與 token 計數尚未執行。此處不提供啟動模型命令；先檢查 fixture 結果，再重查共享資源及準備正常停服流程。max-tokens 預設 256 只是待測輸出預算；新 prompt 必須使用指定 30B tokenizer/chat template 重量 token，不能將歷史 2048 設定視為已足夠。

## 已有幫助與尚未證實

已在局部測試中驗證單一步數上限、提交前資料檢查與失敗保留證據；尚未證實真實模型成功率、延遲、交通安全或整體 memory off。現有停服 EngineDeadError/semaphore 問題仍未處理，不重做 R4/8F。

後續補記：Spark 的 strict/legacy fixture 已通過，詳細證據見 [M07 修正後結果](../M07-relative-source-path/report.md)。先前本地缺 gym 與 Spark 路徑失敗紀錄保留；實際模型回覆及 env.step 尚未執行。
