# M24-R3：新命名 memory-on seed0 完整episode審查

2026-11-26。原回傳 `C:/master's thesis/runs/M24-memory-on-seed0-VW3SSn-review.tar.gz`；解包副本於同層M24-memory-on-seed0-VW3SSn-review。Spark原run `/home/nclab/Yizhen/runs/M24-memory-on-seed0-VW3SSn`，commit239a581efcdee9f311c7cb1c65794a94a856ec84，git工作樹乾淨。

## 結果：流程驗收通過，無CAV碰撞，支持四車到達

| 項目 | 核對結果 |
|---|---|
| episode | seed0，自然終止，101步，303 physics ticks，合計20.2模擬秒 |
| 真Qwen | 505 calls，505份strict回覆解析成功 |
| memory | 初始0，404 queries、404 verified writes，最終404 |
| token | 最大input1107＋output預留256＝1363／2048 |
| 命名 | 101步皆M24-simulation-id，所有road名稱唯一、後綴等於正式ID |
| 受控身份 | 每步submitted_vehicle_actions依序為CAV3、4、5、6 |
| CAV碰撞 | 每步info.cav_crashed=false、保存的final_vehicles均crashed=false |
| 終止 | 最後done=true、四個agents_dones=true，未達249步環境上限 |
| Qwen停服 | exit0、port closed、remaining_known_processes空、warnings空、clean observation=true |
| 驗收結束 | acceptance=PASS、exit code=0 |

四車到達是依未改動的intersection終止邏輯推定：無CAV碰撞、未達時間上限，四個agent都done且episode自然終止；結果未直接保存每車has_arrived布林，不把推定寫成直接量測。

本地以 [audit_vehicle_id_episode.py](../../validation/audit_vehicle_id_episode.py) 再執行既有validate_episode，核對全部rolling corpus、retrieval來源、metadata／write receipt hash、snapshot鏈及服務收尾；新增全101步名稱／ID／CAV動作順序核對。Windows僅stdlib讀JSON，不開Chroma、不載模型。機器可讀結果與全部回傳檔SHA256見 [R3-seed0-audit.json](./R3-seed0-audit.json)。資料庫本體未回傳，所以這不是本地重新開庫驗證，而是Spark服務驗證收據與逐筆資料鏈的重查。

最終logical snapshot：`43a5f971a61c551f962534351c93bf64c57ecf7a4497d232edd7b20f8d32ca28`。

404筆中334筆為原空摘要，約82.67%，共50種stored text。原版memory語義未改，空摘要不代表整場無衝突。不能由此單seed主張memory改善交通，或把與舊99步結果的差異歸因memory。

## 可以開始seeds1–19嗎？

新命名＋真Qwen＋mutable memory的單episode技術驗收已通過，可以進入多seed實驗準備；目前不能直接執行現有舊resume。

這次config與404筆metadata明確為test_only=true，原工具定位是隔離驗收；它不是原M23正式批次的seed0。test_only是來源標記，不表示404筆數值無效，也不是單憑此旗標就必須重跑。然而不能悄悄改寫metadata把它偽裝成正式批次。

若要保留這次seed0並只接1–19，需明確採用「保留M24驗收seed0＋正式延伸」的資料定義，並新增對此run的專用續跑工具：

1. 原test-chroma不以Chroma開啟，先hash／copy到全新正式延伸目錄；原404庫及完整結果不動。
2. 只在新副本開庫，驗證404個ID、text、metadata及上述snapshot完全一致，核對新命名seed0逐步證據；不刪筆、不改test_only=true的原紀錄。
3. 正式後續新寫入標示test_only=false，報告明列seed0來源／commit與延伸工具版本差異。固定同一決策來源、模型、環境、參數與seeds順序；不把工具／來源標記差異藏起來。
4. seed1的initial_count必須404、snapshot必須精確一致；1–19依序共用副本，任一異常保留部分寫入並停止，不自動重試。
5. 新工具必須先以本地替身驗證接受正確404邊界、拒絕錯ID／metadata／snapshot／來源，且Spark副本準備PASS後才啟動交通。這些404續跑工具目前尚未實作／驗收，原始庫也未做任何遷移。

現有 [recover_memory_batch.py](../../validation/recover_memory_batch.py) 鎖定舊efc8a01、舊401→396失敗邊界；不能指定本次目錄或只改seed範圍來繞過。若要求全20seed皆預先定義的正式test_only=false條件，另一方案是全新庫正式0–19；本次只作pilot並完整保留。兩種設計須明列，不能事後只因seed0成功而無說明納入。

本輪僅審查、記錄，未啟動任何Spark或正式續跑。要做純memory on/off效果比較，仍需相同新命名版本的off基線；舊off20seed不覆蓋，不能直接支持純memory因果。
