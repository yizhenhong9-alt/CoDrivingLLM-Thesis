# M07：Python 3.8 相對路徑紀錄修正

日期：2026-11-23。

## 修改前：Spark 原始證據

使用者提供的 runs/20261123T034727Z-a0ccb710/result.json 顯示 Python 3.8.20 下，前四組測試退出碼皆為 0，共 37 項通過。strict fixture 的 command-5.txt 顯示來源雜湊紀錄執行 path.relative_to(ROOT) 時發生 ValueError：validation/run_qwen_single_step.py 是相對路徑，ROOT 是絕對路徑。

失敗在 gym 匯入及環境建構之前，不是模型、GPU、模擬器或套件錯誤。legacy fixture 因 runner 遇錯即停，尚未執行。這裡依使用者提供且本地已讀取的 result.json 與 command-1 至 command-5 日誌判讀，未直接操作遠端。

## 修改內容

[run_qwen_single_step.py](../../validation/run_qwen_single_step.py) 將 Path(__file__) 改為 Path(__file__).resolve()，先轉絕對路徑再記錄相對 repo 路徑。不修改模擬器、提示、parser 或模型設定。

新增回歸測試：從實際 CLI 擷取 source_sha256 指派程式，給相對 __file__，確認仍可記錄入口來源 SHA256。不需要 gym、模型或遠端環境。

統一入口新增 --resume-fixtures，只執行新增的路徑回歸測試與 strict/legacy fixture，沿用既有個人快取、暫存及離線限制，避免重跑已通過套件。

## 修改後結果與限制

本地 Python 3.13 的聚焦測試 13 項全部通過，結果見 [test-results.txt](./test-results.txt)。Python 3.8 grammar 檢查不代替遠端 runtime；Spark 修正後 fixture 尚待使用者執行。

Spark 已通過的 37 項不因這次記錄程式失敗而撤銷，也不需全數重跑。新版全套因新增一項測試變為 38 項；下一次只需執行新的路徑回歸案例，再接續 strict/legacy fixture。若有後續新錯誤，保留新的 console 與 JSON，另作對應修正。
