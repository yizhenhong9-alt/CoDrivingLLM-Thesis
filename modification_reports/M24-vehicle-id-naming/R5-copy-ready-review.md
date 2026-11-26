# M24-R5：Spark 404筆副本準備通過，可接續seeds1–19

2026-11-27。使用者回傳 `C:/master's thesis/runs/M24-review-syipcw4o.tar.gz`，原檔保留，解包至同層M24-review-syipcw4o。使用者詢問能否續跑，並預計啟動後關閉遠端連線。

## 證據核對

- SOURCE.txt：`/home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-PvMXov`。
- 準備commit：4ab0865081a2b686613a9b29abc4f50d6cfc05a4；git-status.txt為空。
- SHA256SUMS中121個檔案全部通過。retained-seed0的116個檔案與先前R3稽核固定SHA256全部相符。
- preparation-console：M24 copy READY、original unchanged、404 records、NO traffic started。
- retained-seed0.json：status=ready、count=404、physical_copy_verified=true、source_unchanged=true。
- snapshot=`43a5f971a61c551f962534351c93bf64c57ecf7a4497d232edd7b20f8d32ca28`，與已審查seed0一致。
- 原庫來源仍為 `/home/nclab/Yizhen/runs/M24-memory-on-seed0-VW3SSn/test-chroma`，收據有六個原庫檔案hash。副本已由Spark既有Chroma環境核對全部ID／text／metadata與含向量logical snapshot；本地只重查收據、hash與證據，不開DB。
- 決策與模型服務來源對seed0 commit239a581未改。seed0仍test_only=true，後續新筆test_only=false，未改寫來源。
- 回傳沒有batch-result.json，符合只準備副本、尚未開始批次的狀態；不是已完成1–19。

## 結論與啟動

副本準備驗收通過。可由使用者手動使用 [resume_m24_memory_on.sh](../../validation/resume_m24_memory_on.sh) 指定上述PvMXov目錄，啟動seeds1→19；保留已完成seed0，不重跑、不覆蓋原庫。每seed上限300步／3600秒，跨seed累積，異常即停、不自動重試。這是保留pilot seed0＋正式延伸的序列，非宣稱全部20seed起初皆正式標記，亦非純memory因果證明。

啟動時使用nohup、stdin=/dev/null、stdout/stderr導向全新launcher目錄，再disown。正常SSH／VS Code遠端斷線通常不影響該背景程序；主機重啟、管理政策終止程序、OOM或程式錯誤仍會停止，因此不保證任何情況都持續。

批次總log是launcher/nohup.txt；逐seed細節位於PvMXov/seed-01/console.txt等。管理器的進度輸出先進逐seed檔案，總log可能到seed驗證完成後才更新。seed01檔案沒出現時先看launcher log及PID，不重啟另一份。Ctrl+C退出tail不停止批次。

腳本正常結束或捕捉到失敗後會收集白名單證據，印出Review archive的確切路徑；回傳該tar.gz。若主機或程序被強制終止，finish trap可能未執行，應先回傳launcher log，不盲目重跑。本輪Codex僅查證與提供手動指令，沒有SSH／啟動Spark程序。R4既存未提交刪除保留。
