# M11：虛擬環境 interpreter 路徑檢查修正

日期：2026-11-23。

## 修改前證據

使用者執行 M10 後，console 為 argparse error: All paths must stay inside /home/nclab/Yizhen。該檢查在建立輸出資料夾與 Popen 前，故這次沒有透過此工具啟動模型，也沒有執行 API 或停服流程。

原檢查對 output/repo/model 及兩個 python executable 全部呼叫 resolve().relative_to(OWNER)。venv/bin/python 可能是連到系統或受管理的基礎 interpreter 的 symlink；解析後在個人目錄外是合法情況，不等於程式要寫入系統 Python。本地以 mocked symlink target 重現原 guard 的拒絕。

原錯誤沒有列出失敗路徑，尚未取得 Spark 的實際 symlink target，因此不能僅憑這個 console 宣稱已確認唯一遠端根因。

## 修改內容

[run_qwen_live_session.py](../../validation/run_qwen_live_session.py) 新增 validate_session_paths：

- output/repo/model 仍檢查解析後目錄必須在個人範圍。
- interpreter 的呼叫位置與解析後 bin 目錄仍須在個人範圍，但允許 executable 自身的 symlink 指向外部基礎 Python；只執行/讀取，不改動、不安裝。
- 仍要求指定 inference 的 sys.prefix，防止誤用系統環境。
- 失敗訊息列明欄位、傳入路徑與解析結果；成功時在 result.json 保存 checked_paths。

沒有移除整體路徑限制，沒有更動模型、記憶體設定、提示或停服策略。

## 修改後測試

本地 Python 3.13 的 M10/M11 聚焦測試共 12 項通過，見 [test-results.txt](./test-results.txt)。新增三項：重現原 guard 對外部 executable symlink 的拒絕並驗證新 guard 接受；外部輸出仍拒絕且顯示路徑；外部 interpreter 呼叫位置仍拒絕。

沒有建立真實系統 symlink、啟動模型或發 signal。這是本地 policy 測試，不代替 Spark 執行結果。

## 尚待驗證

Spark 更新後接續原 M10 命令；若仍被擋，回傳新訊息中的具體路徑，不自行移動環境、修改 symlink、安裝套件或擴大權限。已通過 M01–M09 不重跑。模型實際啟停與回覆仍未完成。
