# M24-R2 新命名 memory-on seed0 單episode驗收

2026-11-26。M24-R1的Spark seed0/1零步fixture與10份token計數均通過；使用者要求從memory on開始下一步，並指定accept_memory_episode.py。因此準備單一seed0完整episode，尚未在Spark執行，不是20seed正式批次。

新增 [啟動腳本](../../validation/accept_vehicle_id_memory_episode.sh)，呼叫既有 [accept_memory_episode.py](../../validation/accept_memory_episode.py)。保留既有服務環境、管理器、原版memory語義、strict、2048context／256output、300步／3600秒上限與停止／停服流程。建立全新M24-memory-on-seed0-*目錄與test-only空Chroma庫；不開舊401／396庫，不沿用M23 seed0，不自動重試或跨seed續跑。單episode成功後的庫也只作本次驗收，不自動升格正式20seed起始庫。

真Qwen協商與動作回覆、原版逐車retrieve→決策→write→全車完成後step，以及同一步後車可檢索前車寫入均會實際執行。原驗收核對自然終止、逐筆來源／metadata／hash、rolling snapshot、token budget與Qwen正常停服。碰撞可構成自然終止，流程PASS不等於無碰撞或全車到達；需回傳原始結果另判交通結果。

新增wrapper在底層腳本非零結束後仍收集白名單JSON、console、git資訊及exit code，壓縮檔輸出於run目錄外。記憶資料庫、cache及模型不回傳，但原檔留在Spark供後續查證。外部人工中斷或機器故障仍可能使打包未完成，不能宣稱任何失敗都必有完整archive。

執行與回傳由使用者手動，Codex不SSH、不啟服務。回傳後須核對各步M24-simulation-id、全road文字名稱唯一且與ID一致、CAV身份、真模型解析、記憶讀寫與token、交通終止原因及停服。不代表已授權／執行20seed或舊resume。
