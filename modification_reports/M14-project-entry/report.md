# M14：將 Qwen 流程接入正式主入口

日期：2026-11-23。

## 修改前與目的

[Run_multi_CAV_LLM.py](../../Run_multi_CAV_LLM.py) 原先在載入時直接匯入雲端 SDK 及建立模擬，固定執行 100 回合；模型呼叫仍走原本的雲端 agent。M10/M12 已證明專用 validation 入口可以向真實 Qwen 取得回答並執行一次 step，但不能作為正式主入口整合成功的證據。

本次將原流程包進 legacy_main，新增明確 backend 選擇；不是把 validation 腳本複製成主程式。Qwen 模式共用 [qwen_step.py](../../llm_controller/qwen_step.py) 的 prompt、parser、車號與動作檢查，並由 [qwen_episode.py](../../llm_controller/qwen_episode.py) 負責有上限的逐步迴圈。原 agent 的場景／衝突／安全相關方法繼續被呼叫。

## 修改範圍

- 正式主入口要求 --backend qwen 或 --backend legacy，避免直接執行就誤跑 100 回合。Qwen 預設最多 1 步、1800 秒；一次只建立一回合。到步數上限記為 step_limit_reached，只有環境 done 才記 episode_terminal。terminal 可能是碰撞、到達或環境時間到，不等於成功駕駛。
- 原雲端迴圈、video／Excel 行為保留在 legacy_main，僅明確 --backend legacy 才進入。Qwen 模式目前輸出 JSON／Markdown，未接入原 video／Excel 輸出；不宣稱所有原輸出功能完全等價。
- 兩個 agent 的 OpenAI 匯入改由 [cloud_client.py](../../llm_controller/cloud_client.py) 延遲載入。只有呼叫原雲端方法時才需要 SDK；Qwen 正式路徑不使用 M05 的 SDK 替身。原 parser、原 send_to_chatgpt 方法本體保留。
- 共用 run_step 增加 step_id（預設 0 保持單步相容），逐步檢查不再固定寫 0。每步重取場景與可用動作、重新詢問模型；沒有重放 fixture 或舊回答。
- 每次執行保存版本、工作樹狀態、程式 SHA256、設定、實際步數、memory 狀態；每步保存完整 messages、raw_response、API response、兩種 parser 結果、提交動作與步進前後狀態。失敗先落盤，停止而不補 IDLE 或重試。
- negotiation／action 分別統計 attempted、text_received、no_text，以及 strict／所選 parser 的解析數與比例。比例分母是收到的完整文字回答，無回答另列；解析率不是決策正確率，也不是 parser 公平比較。
- 自動產生 review.md，逐步列出模型原文與 parser 結果，並連結包含完整 prompt 的 step JSON。
- [run_qwen_live_session.py](../../validation/run_qwen_live_session.py) 新增 --project-entry，啟動服務後真正呼叫正式主入口；沿用既有資源檢查、個人快取與只停 API parent 的流程，不改 vLLM 啟動參數。每次 HTTP 有 timeout，回合每次請求前檢查剩餘時間；wrapper 另有時間上限加 60 秒清理寬限，超時只終止自己啟動的 client。

原安全公式、交通優先權、提示前 5 m/s 截速與 memory off 保留。兩個 LLM 邏輯角色與 M05/M12 相同。本次仍僅支援 intersection；其他場景需另行整合，不依場景名稱猜測動作。

## 修改後本地驗收

[check_project_entry.py](../../validation/check_project_entry.py) 新增 11 項測試全部通過，輸出見 [test-results.txt](./test-results.txt)。涵蓋正式入口派送、匯入時不啟動模擬或載入雲端依賴、連續三步／不同 step ID、done 提早結束、第二步錯車號不執行該步且保留回答、fixture 禁止推進、deadline、解析統計、延遲 SDK、wrapper 指向正式檔案，以及 Python 3.8 語法。

相關回歸測試另通過：check_memory_off 5 項、check_qwen_single_step 14 項、check_live_session 13 項；共 43 項。本地是 Python 3.13.13 與替身環境／HTTP，不載入模型；語法檢查不等於 Python 3.8 真實套件整合通過。正式入口 --help 已驗證可用。未在本地安裝 gym 或載入權重。

## Spark 下一次驗收：正式入口連續最多三步

先同步 Git，確認工作樹，再使用既有 inference Python 啟動管理入口：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git status --short
git pull --ff-only origin qwen-local
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/run_qwen_live_session.py --project-entry --parser strict --seed 0 --max-steps 3 --wall-seconds 600 --output-dir /home/nclab/Yizhen/runs/M14-project-entry
```

--project-entry 自動用既有 simulation Python 執行 Run_multi_CAV_LLM.py --backend qwen；不要再加 --apply-step。服務仍只有一份指定 Qwen 30B FP8。啟動前重新檢查當下 RAM／GPU／埠，會使用共用硬體，但新增快取及結果限個人目錄，不動其他人程序。

若已有自己的合規 Qwen 服務，主入口也可直接執行（它本身不啟停服務）：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python Run_multi_CAV_LLM.py --backend qwen --parser strict --seed 0 --max-steps 3 --wall-seconds 600 --output-dir /home/nclab/Yizhen/runs/M14-project-entry-direct
```

驗收應檢查 wrapper 的 project_step_limit_reached／project_episode_terminal 與 clean_observation；traffic 下的 result.json、review.md 及 step-*.json 需一起查看。預期最多三步，若環境更早 terminal 就停止；原文、車號、動作、步數與失敗原因皆需核對。這是正式入口接線驗收，目的不同於重做舊單步測試。

## 尚未取得的證據

本次尚未在 Spark 執行 M14，不能宣稱正式入口已跑通、完整回合已完成或解析率提高。待使用者回傳整個新執行目錄，再補實測與修改前後比較。三步驗收後再安排完整一回合；完整回合仍須區分正常到達、碰撞、環境時限、程式上限與解析失敗。

## 後續 Spark 回傳：啟動階段失敗

使用者已執行 20261123T084407Z-0ea03d24。已讀取結果與服務日誌：RPC socket 完整路徑 108 bytes，超過 107 bytes，服務未 ready 就 exit 1；traffic_command 尚未建立，正式主程式沒有執行。埠已關、已知程序無殘留，不能將 needs_shutdown_review 當作殘留證據。修正與驗收安排另見 [M15](../M15-short-rpc-path/report.md)。

回傳資料更正：只需 result.json、server-console.txt、traffic-console.txt 及 traffic 內 JSON／Markdown，無需下載整個含 socket／cache 的目錄。
