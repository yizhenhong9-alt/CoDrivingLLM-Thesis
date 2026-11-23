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
| M09 | 真實 API 前資源與停服證據檢查 | [report.md](./M09-live-preflight/report.md) | Spark 快照與原啟動/停服證據已核對；不是資源預留 |
| M10 | 真實回覆與主程序停服入口 | [report.md](./M10-real-response-session/report.md) | Spark 真實協商/action 解析及本次正常停服通過，0 步 |
| M11 | venv interpreter 路徑檢查修正 | [report.md](./M11-venv-path-guard/report.md) | Spark 成功執行，確認 inference 基礎執行檔為 /usr/bin/python3.12 |
| M12 | 真實單步控制入口 | [report.md](./M12-one-step/report.md) | Spark 真正 1 步／0.2 秒與正常停服已核對；不能推論完整回合安全 |
| M13 | 負距離來源審查 | [report.md](./M13-signed-distance-audit/report.md) | 原 function 重現 -6.59；abs 後仍不等於中心距，不改公式 |
| M14 | Qwen 接入正式主入口 | [report.md](./M14-project-entry/report.md) | 本地整合通過；Spark 因 RPC 路徑過長啟動失敗，尚未執行正式入口 |
| M15 | RPC socket 短路徑修正 | [report.md](./M15-short-rpc-path/report.md) | 重現 108 bytes 超過 107；短路徑 73 bytes，30 項本地測試通過，Spark 待驗證 |

原版 agent 保留；後續真實 Qwen 回覆與 Spark 結果補入各報告，不覆蓋歷史證據。未執行項目不預先宣稱通過。
