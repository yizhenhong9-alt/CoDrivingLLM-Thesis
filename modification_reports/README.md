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
| M14 | Qwen 接入正式主入口 | [report.md](./M14-project-entry/report.md) | M15 修正後 Spark 正式入口實際三步通過；完整回合待驗證 |
| M15 | RPC socket 短路徑修正 | [report.md](./M15-short-rpc-path/report.md) | Spark 啟動及正常停服通過；正式入口三步、15/15 strict 解析，非跨場景保證 |
| M16 | 正式入口一回合實測 | [report.md](./M16-one-episode/report.md) | seed 0 跑完 101 步；505/505 strict 通過、CAV 無碰撞，依原條件推定全車到達出口，正常停服 |

原版 agent 保留；後續真實 Qwen 回覆與 Spark 結果補入各報告，不覆蓋歷史證據。未執行項目不預先宣稱通過。

M17：[離線 prompt 一致性審查](./M17-prompt-consistency-audit/report.md)；404 份 action prompt 中 89 份存在無衝突句與通行建議並存，已提出文字修正範圍，未改正式 prompt／控制行為。

M18：[intersection 20 seeds memory off 審查](./M18-intersection-memory-off-20seeds/report.md)；推定全車無碰撞通行 9/20（45%）、CAV 碰撞 7/20、時間上限 4/20；11625/11625 保存 strict 解析成功，seed 17 停服警告保留。

M19：[memory on 原流程審查與實作範圍](./M19-memory-on-audit/report.md)；原流程與後續 M20–M23 分工，未啟用 memory on。

M20：[本地記憶底層第一版](./M20-local-memory/report.md)；最新 [R1 Chroma 補充](./M20-local-memory/R1-chroma/report.md) 改採本地 embedding＋Chroma 方向，SQLite 保留參考；本地替身通過，Spark 與真 embedding 待驗，正式 memory off 未改。

M20-R2：[原版 memory 語意與差異審查](./M20-local-memory/R2-memory-semantics/report.md)；M16 404 筆離線重播，367 筆空資訊、query／存入文字只差前導換行；列出寫入時機、欄位、檢索回傳與 M20 差異，未執行 memory on。

M20-R3：[原格式欄位對照與 Chroma 驗收準備](./M20-local-memory/R3-chroma-acceptance/report.md)；凍結原方法測試案例、加入跨程序重開驗證與 Spark 手動腳本，本地替身通過，真 Chroma 與 MiniLM 待驗。

M20-R4：[MiniLM CPU 相依規劃](./M20-local-memory/R4-minilm-runtime-plan/report.md)；R3 已在 Spark 14/14 通過，現在以完整已驗證版本清單約束新相依，只做 dry-run；MiniLM 尚未下載／載入。

M20-R5：[MiniLM CPU runtime 安裝與回歸準備](./M20-local-memory/R5-minilm-runtime-install/report.md)；R4 已解析通過，固定 9 個新增套件，驗證 CPU imports／tensor 與 Chroma 回歸；Spark 待執行，無模型下載／載入。

M20 最新狀態（歷史段落保留）：R5 已在 Spark 通過，89 套件基線固定。

M20-R6：[固定 MiniLM 真向量驗收](./M20-local-memory/R6-minilm-embedding-acceptance/report.md)；e267270 Spark PASS／exit 0，來源 hash、受限 CPU 轉換、兩筆原模板 metadata／top-1／same-process reopen 通過；不代表全面交通語意或 production on 完成。

M20-R7：[跨環境 localhost memory HTTP](./M20-local-memory/R7-memory-http/report.md)；單一 encode→Chroma 服務與 Python 3.8 stdlib client、隔離跨程序驗收已實作，本地替身通過；Spark 手動驗收待執行，正式 memory off／M21／M22 尚未改。
