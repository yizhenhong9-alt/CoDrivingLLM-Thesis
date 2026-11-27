# M24-R6：seed3漏答協商、批次停止與800筆邊界審查

2026-11-27。使用者回傳 `C:/master's thesis/runs/M24-review-srbknpjg.tar.gz`；原檔保留，解包至同層M24-review-srbknpjg。Spark原run仍為 `/home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-PvMXov`，執行commit4ab0865081a2b686613a9b29abc4f50d6cfc05a4。本輪僅本地讀證據，不SSH、不啟動交通、不開Chroma、不修改prompt或安全公式，不操作共用帳號其他人的檔案／程序。

## 已驗證結果

261個匯出檔SHA256全部通過。保留seed0的固定證據亦通過既有load_evidence；seed1、2重跑原validate_episode，並對seed3完成步驟逐筆檢查query來源、metadata、write receipt與rolling snapshot。見 [稽核JSON](./R6-stopped-batch-audit.json) 與 [stdlib稽核工具](../../validation/audit_m24_stopped_batch.py)。本地不含DB，快照與資料一致性依Spark收據及逐筆證據鏈確認，不宣稱已本地驗證DB還原。

| seed | 實際狀態 | 完成步數 | Qwen calls | 記憶筆數 |
|---|---|---:|---:|---|
| 0 | 保留M24驗收，四車到達推定 | 101 | 505 | 0→404 |
| 1 | 自然終止，CAV3碰撞 | 58 | 290 | 404→636 |
| 2 | 自然終止，CAV3、4碰撞 | 41 | 205 | 636→800 |
| 3 | step15協商拒絕，未完成episode | 15 | 76 | 800→860 |
| 4–19 | 未啟動 | — | — | — |

seed1、2的碰撞是有效觀測，不是程式錯誤，也不是本次批次停止原因。seed3在15個完成步驟未記錄CAV碰撞，但不能稱成功到達。觀測模擬時間分別為seed1=11.533333秒、seed2=8.066667秒、seed3=3秒；使用保存physics ticks，不用步數乘0.2取代實際觀測。

三個seed的Qwen shutdown均exit0、port closed、remaining_known_processes空、warnings空、clean_observation=true；seed3的memory session亦closed=true、final_snapshot_verified=true。批次console正常完成collector並exit1。batch-result頂層stopped_requires_review是實際結果；seed3 row仍寫running是失敗前狀態未被更新的摘要殘留，不表示背景仍跑。沒有為此修改原結果。

## 直接失敗原因

seed3/step-0015.json的prompt要求Pairs `[[3,2],[4,3]]`；模型只回覆 `{"decisions":[{"first_vehicle":3,"second_vehicle":4}]}`。3→4處理了無向pair{3,4}，漏掉{2,3}。以現有parse_negotiation重播同一raw，精確重現Missing conflict decisions。

API使用量prompt490、completion16，finish_reason=stop。回覆逐字等於prompt中固定JSON示例。支持「可能照抄範例／未遵循完整pair清單」這個假說，但不能僅憑一次觀測證明心理／推論根因。這個固定範例與strict完整pair檢查在M05已存在，舊M18 memory-off亦使用；不是M24 memory-on才加入。

失敗step只有1個negotiation call、memory_queries=[]、memory_updates=[]、沒有step_attempted；actual_environment_steps仍15。60筆是前15步每步四車的已驗證寫入，不是失敗協商後又寫入。協商prompt未注入memory經驗，不能把這次漏答直接歸因memory內容或embedding；memory仍可經先前動作與軌跡間接影響這個場景。

該seed車2是MDPVehicle #2（CAV）；HDV為IDMVehicle #0／#1。不能套用seed0的「HDV0–2、CAV3–6」推斷所有seed；ID隨episode reset分配。本次完成步驟的名稱與ID一致，未發現原餘數撞名復發。

## 已確認的恢復邊界與限制

seed2結束800筆snapshot：`e3b4429eef5e0508784dee80821bed5d8996824ecbd1aa5f243210faac34c787`。

seed3失敗後860筆snapshot：`c87691df4faa150eede66d0fde4b30a7b5e28fc6d7ca74a58e3ea3b8f88f3c94`。

稽核確認800個保留ID與60個seed3新增ID完全分離，60筆清單存於R6-stopped-batch-audit.json的partial_ids。若選擇從seed3開頭重試，必須另建副本，在副本驗證860筆與全部ID／text／metadata，再只排除這60筆、核對800筆snapshot；原860庫與全部失敗記錄保留。logical snapshot相同不保證刪除後HNSW索引或tie邊界位元級還原，不能聲稱完全回到同一索引狀態。

目前舊401→396恢復工具與M24 seed0 404續跑工具都不支援這個860→800邊界，**沒有執行還原，也沒有提供可直接重啟的通用命令**。不可直接重跑resume_m24_memory_on.sh、將860當800，或關掉strict guard來讓漏答通過。

## 下一步須區分實驗設計

保留本次完整失敗觀測是第一步。若維持同一prompt重試，需明確記錄protocol retry與新attempt，不能以重試結果覆蓋原失敗／宣稱首次成功；也不能靠反覆重試挑成功。

若改掉固定範例或強化完整pair指示，就是新的negotiation content版本；應先對凍結失敗prompt及其他多pair情境做隔離驗收，仍保留完整pair guard，不改安全公式／優先權。不能把改後seed3–19直接稱為原版本20seed memory-on。新版本要與同版本off比較，或明列分段版本與混雜。現有source fingerprint會拒絕悄悄修改qwen_step後沿用保留seed0工具，這個拒絕應保留，不能繞過。

本輪未做上述任何prompt修正、正式重試或Spark副本準備；只新增本地稽核工具與報告。R4既存未提交刪除保留，原作者副本未修改。
