# 修改紀錄索引

每項修改使用固定編號與名稱。報告分開記錄原版觀察、新版測試與尚待驗證事項；離線測試通過不等於交通安全或模型能力改善。

| 編號 | 名稱 | 報告 | 狀態 |
|---|---|---|---|
| M01 | JSON 回覆解析 | [report.md](./M01-json-parser/report.md) | 原版問題已重現，新版離線測試通過；未正式接線 |
| M02 | 場景動作設定 | [report.md](./M02-scene-actions/report.md) | 程式與離線測試已建立；結果見報告 |
| M03 | 車號與多車動作檢查 | [report.md](./M03-vehicle-actions/report.md) | 程式與離線測試已建立；結果見報告 |
| M04 | 真正 memory off 入口 | [report.md](./M04-memory-off/report.md) | 實際入口已修改；5 項本地離線測試通過，未跑完整模擬 |
| M05 | Qwen 專用單步入口 | [report.md](./M05-qwen-single-step/report.md) | Spark strict/legacy fixture 已通過；真實 Qwen 回覆與 step 待驗證 |
| M06 | Spark 離線驗證與同步準備 | [report.md](./M06-spark-offline-validation/report.md) | 統一驗證入口與個人快取設定；Spark 結果待補 |
| M07 | Python 3.8 相對路徑紀錄修正 | [report.md](./M07-relative-source-path/report.md) | Spark 新回歸測試及 strict/legacy fixture 已通過，原失敗證據保留 |
| M08 | 新版提示 token 計數 | [report.md](./M08-prompt-token-budget/report.md) | Spark 3.12 已完成 10 筆計數；輸入加 256 預算全部符合 2048，最大 1242 |

原版 agent 保留；後續真實 Qwen 回覆與 Spark 結果補入各報告，不覆蓋歷史證據。未執行項目不預先宣稱通過。
