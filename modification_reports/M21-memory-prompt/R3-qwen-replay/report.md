# M21-R3：兩筆真檢索 prompt 的零步進 Qwen 回答驗收

2026-11-25。配置、來源 guard、tokenizer preflight、真回答驗收入口及本地替身測試已實作；Spark 尚待使用者手動執行。正式 memory off、factory on 拒絕、run_step fixture-only gate 均未修改；未接 M22 更新。

## 基線與編號

開始時 qwen-local／709957b，工作樹乾淨。R2 已審查成功，兩筆實際 MiniLM／Chroma 候選及完整 prompt 保存於 `/home/nclab/Yizhen/runs/M21-R2-retrieval-prompt-6fIklV`。本次只重播這兩份已核對的 prompt，不重建 R2 DB、不重跑 M16／20 seeds、不修改原作者副本，不下載／安裝模型／套件或重新部署 Qwen。

| 編號 | 變更 |
|---|---|
| M21-R3-01 | [memory_replay.py](../../../llm_controller/memory_replay.py)：明確 frozen-test 配置、R2 三份檔案 hash、原 M16 source／prompt／query／manifest／snapshot／候選與 token receipt 核對；兩次 strict action 請求與逐次保存 |
| M21-R3-02 | [prepare_memory_replay.py](../../../validation/prepare_memory_replay.py)：對已審查 R2 證據的三個固定 SHA256，產生本次 replay-config.json，再以現有本地 Qwen tokenizer 重算兩份完整 messages；不載入模型權重 |
| M21-R3-03 | [run_memory_prompt_replay.py](../../../validation/run_memory_prompt_replay.py)：既有 Python 3.8 stdlib client，只送兩份保存 prompt，驗證 strict parser，無 gym／env 建構或 env.step |
| M21-R3-04 | [run_qwen_live_session.py](../../../validation/run_qwen_live_session.py)：明確 --memory-replay-config 分支，拒絕搭配 --apply-step／--project-entry／legacy，沿用原啟動、資源／埠／ownership guard、parent-only stop 與殘留檢查；補單命令 git safe.directory，不改全域設定 |
| M21-R3-05 | [accept_memory_qwen.sh](../../../validation/accept_memory_qwen.sh) 與 [check_memory_replay.py](../../../validation/check_memory_replay.py)：使用者手動入口、配置／兩次呼叫／失敗保存／零步進／既有生命週期回歸 |

## 本關精確範圍

本次是**已驗證真檢索結果的凍結 prompt 重播**：R2 曾真 HTTP 檢索，R3 重用其實際候選／順序／文字，核對來源後送真 Qwen。不是每次生成前重新檢索，不是即時模擬場景，也不會更新 memory。分開兩關讓此次 GPU 工作只驗證「這兩份帶記憶 prompt 能否產生合法回答」，不重做已通過的 CPU DB 驗收。

新增配置只供此測試模式，不是正式應用 memory-on CLI／通用生命週期已完成。正式即時檢索的 tokenizer 計數介面、每回合 client 生命週期及 M22 逐車步前更新仍待接線。原版跨 episode 共用庫與後車可讀前車當步寫入的語義未被本次凍結測試取代，不宣稱僅換 embedding 後完全等價。

兩份 prompt 仍為 R2 原注入文字，不改四欄、generate_comment、negotiation、安全規則／公式／門檻／優先權／signed distance／速度處理；不多送 negotiation 請求。每次回答必須是現有 strict schema 的合法 vehicle_id／decision，使用原保存 available_actions 驗證。**合法回答不等於駕駛正確、安全或更好**；回答不需要與 memory off 相同，也不要求服從某筆歷史動作。沒有 env、交通後果或安全效果證據。

## 啟動與錯誤行為

先在既有 Qwen 3.12 環境做 tokenizer-only preflight：固定 R2 證據 hash、原 M16 hash、完整 messages hash／query／候選順序、manifest／snapshot／counts receipt 一致；再以本地 tokenizer／chat template 重算，預期 1129／949，input＋256 ≤2048。所有 cache 在本次個人 run、offline、socket block；這個 Python 結束後才啟動已部署的 Qwen。

沿用既有 vLLM 0.34.0、同一官方 30B FP8 目錄／served name／2048 context／GPU utilization 0.40／原 KV cache、Triton、短 RPC path、shutdown-timeout 30。啟動前重新檢查 available RAM（既有保守 gate）、GPU UUID、18080 是否空閒與程序 ownership。不使用他人已有 listener，不改原共享資源設定。是重新啟動已部署模型作新驗收，不是重新安裝或部署。

資料 hash 或 token 不符在啟模型前停止；回覆逾時、finish_reason 非 stop、拒答、JSON／車號／動作錯誤則停止，不重試、不補 IDLE。逐次保存完整 messages、raw_response、API response（含未完成回覆）、parse 結果或錯誤，失敗時亦保留。API parent 仍只 SIGTERM 並等待最多120秒，後續只觀察殘留，不 SIGKILL／killpg／動他人程序。外層 needs_shutdown_review 必須保留，不能因兩筆 parser 成功就宣稱完整 PASS。

## 本地測試與限制

Windows 既有 Python 3.13.13／stdlib／替身，PYTHONDONTWRITEBYTECODE=1；未下載／載入模型或 tokenizer，未操作 Spark／SSH／GPU／網路服務或模擬。新測試涵蓋配置與來源 hash、manifest、超 token、source 變動／路徑越界拒絕；兩次 exact prompt、strict parse、完整回覆保存、零步進；錯車號與 timeout 只呼叫一次就停止；驗收結果不能冒稱有步進／漏 parse；CLI 分支衝突；Python3.8 AST／不匯入 ML。

首次新測試有 1 error／1 failure，因 Windows test fixture write_text 將 commit 換行寫成 CRLF，測試卻對 LF 字串算 hash；來源 byte guard 正確拒絕，後續失敗保存測試尚未發請求。已改測試用 write_bytes，保留 production 的 byte hash 嚴格檢查，不放寬換行。最終測試與 source SHA256 見 [test-results.json](./test-results.json)，逐項 console 同目錄。五個新增／修改 Python 檔編輯器無錯誤。Spark 真 tokenizer／模型回答／停服本次尚無證據，Bash 未在 Windows 實跑。

最終合計 48 通過、0 略過：check_memory_replay.py 10、check_live_session.py 13、check_project_entry.py 11、check_memory_off.py 5、check_memory_prompt.py 9，五個命令 exit 0。console 中部分空行顯示 System.Management.Automation.RemoteException，是 PowerShell 對 native stderr 的物件包裝，不是 Python traceback；逐項結果與 exit code 如實保存。

## Spark 使用者手動操作

先核對分支／工作樹，無修改才 pull。這次會啟動既有 Qwen 並使用共用 GPU／RAM；執行前檢查當下資源，18080 若已有 listener 就停止本次操作，不結束或借用別人的服務。memory 18082 不需要啟動。

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
# 確認 qwen-local 且無未提交修改後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
df -h /home/nclab/Yizhen
nvidia-smi
ss -ltn 'sport = :18080'
# 確認沒有 listener 後：
bash validation/accept_memory_qwen.sh
```

結果根目錄 `/home/nclab/Yizhen/runs/M21-R3-memory-qwen-*`；tokenizer preflight 先 PASS，之後既有管理器在 live/<run>/ 保存模型與 traffic 紀錄。預期外層 status=responses_validated、exit 0，traffic/result.json 的 status=memory_responses_validated、actual_environment_steps=0、qwen_calls=2，兩筆都有 parsed_action，且 shutdown.clean_observation=true。這不是單步，也沒有重跑某個 seed。

請回傳完整 console、根目錄 git-commit.txt／preflight.json／replay-config.json、live/<run>/result.json、live/<run>/traffic/result.json。若停服／啟動有異常，再回傳 server-console.txt 與 traffic-console.txt；不要下載 cache／RPC／模型。失敗結果保留，不重啟測到成功、不更換版本或放寬 token／parser。
