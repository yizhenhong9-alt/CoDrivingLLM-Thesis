# M24：一致 vehicle.id 命名與新 off 基線評估

日期：2026-11-26。起點 HEAD：4c85468，branch qwen-local。

## 結論與授權邊界

已將 Vehicle 字串改為正式 `vehicle.id`；沒有改安全公式、門檻、優先權、signed distance 或速度處理，也沒有套用 M17。此修改**會改完整 prompt 的文字與 token**，不能據此宣稱 Qwen 回答不變、改善決策，或與舊 off 的差異只來自 memory。

若論文問題是隔離 memory on/off，在完成新版本驗收後，需要另建同版本、新命名的 off seeds0–19 基線；on 也須從 seed0、全新空庫依序開始。這是必要性評估，**沒有啟動或授權任何正式重跑**。舊 M18 off 是有效的舊版本觀測，原資料與失敗資料均保留，不覆蓋、不刪除、不挑 seed／重試結果。

## 查證範圍與身份生命週期

- [AbstractEnv.reset](../../highway_env/envs/common/abstract.py)：`_reset` 建立 road、HDV、CAV，之後依最後 road.vehicles 順序分配 `v.id=i`。初始 ID、車輛順序及亂數呼叫不變；每次 reset 建立新的 road。
- [IntersectionEnv](../../highway_env/envs/intersection_env.py)：初始化 `_spawn_vehicle` 的車輛在 reset 尾端取得 ID。現行 step 的動態 spawn 呼叫是註解，故目前正式路徑沒有每步新生車。仍補足 reset 後主動呼叫 spawn 的身份：成功加入 road 前從 episode 高水位取新 ID；刪車不回收 ID，失敗 spawn 不消耗 ID。
- [Vehicle](../../highway_env/vehicle/kinematics.py)、[ControlledVehicle](../../highway_env/vehicle/controller.py)、[IDMVehicle](../../highway_env/vehicle/behavior.py)、[IntervalVehicle](../../highway_env/vehicle/uncertainty/prediction.py) 四個 create_from 實作：原本不複製 ID，現在來源有 ID 才承接。包括 road 記錄 history 的快照與 change_vehicles 類別替換；deepcopy 原本就保存屬性及身份數值。這些是同一模擬身份的副本，不能把原件與副本同時當作不同實車插入同一 road；EpisodeVehicleMap 會拒絕重複 ID。
- reset 前的建構／預熱 history 可能沒有 ID，字串明確顯示 `#unassigned`，不使用 Python 位址猜身份，也不符合數字 regex。此類物件不能成為決策輸入：EpisodeVehicleMap 先拒絕缺失、非法或重複 ID。未替其他場景新增自動分配器。
- [EpisodeVehicleMap](../../llm_controller/vehicle_actions.py) 保留缺失／重複 ID、同 mapping 內物件替換及動作期間順序變動等拒絕。run_step 每步建立 mapping，並非宣稱它跨步偵測全部替換。
- RoadObject 的位址除錯名稱未變：Obstacle／Landmark 不是這裡的 Vehicle，不在 CAV／HDV 的協商 regex 與 road.vehicles 身份鏈內。graphics 的有效顯示原本已使用 v.id。

## 文字與反查鏈

[Vehicle.__str__ / __repr__](../../highway_env/vehicle/kinematics.py) 統一輸出 `Class #<vehicle.id>: position`，維持 MDPVehicle／IDMVehicle 類別文字與十進位格式，不做取餘數。所有使用 str(vehicle) 的完整場景、協商、工具、安全分析與記憶摘要自動使用相同名稱。

[qwen_step](../../llm_controller/qwen_step.py) 的 mapping → 協商 prompt → strict 整數回覆 → 原 helper 文字 bridge → [extract_vehicle_conflicts / transfer_negotiation_prompts_to_results](../../llm_controller/llm_agent_action.py) → [check_safety_with_conflict_vehicles](../../llm_controller/prompt_llm.py) 的 regex 與 str 比對，仍維持同一名稱來源。另一份 [envs/prompt_llm](../../highway_env/envs/prompt_llm.py) 的車輛文字也由相同 Vehicle 字串取得。沒有只替換 LLM names。

保留名稱碰撞 guard 及診斷欄位，強制同名字串仍在任何決策 call 前拒絕。報告新增 `vehicle_label_version=M24-simulation-id`；歷史 `legacy_label` 欄位名稱保留相容性，現行值是新名稱。`prompt_version` 的 M05／M22 表示原模板／流程，不足以單獨辨識本次命名版本，須同看 label version、commit 與 source hash。

## 本地驗證

Windows Python 3.13.13；設定 PYTHONDONTWRITEBYTECODE=1；無模擬器／模型／embedding 載入，無新增套件。

| 驗證 | 結果 |
|---|---|
| [check_vehicle_labels](../../validation/check_vehicle_labels.py) | 6/6 PASS |
| [check_qwen_single_step](../../validation/check_qwen_single_step.py) | 15/15 PASS |
| [check_vehicle_actions](../../validation/check_vehicle_actions.py) | 13/13 PASS |
| [check_memory_off](../../validation/check_memory_off.py) | 5/5 PASS |
| [check_safety_dispatch](../../validation/check_safety_dispatch.py) | 5/5 PASS |
| [check_original_memory](../../validation/check_original_memory.py) | 13/13 PASS |

合計57項。新測試以 AST 載入實際來源方法配合 stdlib 替身：R6 兩個實際物件位址同餘624而正式3/6各自命名；1003不取餘數；repr／deepcopy；四個 create_from；移除後 spawn 不回收 ID；真 regex／文字橋接；完整 strict fixture flow；相同物理狀態、相同指定先後順序下，重新命名後安全分析與 delta TTCP 完全相等，錯誤名字不會命中該車。這是局部數值與接線驗證，不是 Qwen 行為不變證明。

新完整流程測試初版因 mock 對 class.__name__ 的清理方式失敗，已改為真實命名子類後重跑6項全通過；不是交通或模型失敗。git diff --check 通過；新測試與 qwen_step 編輯器診斷無錯。

限制：reset 分配尾段有來源檢查，未在 Windows 執行真 reset；spawn、copy 與安全 helper 使用真方法與替身執行。未宣稱 Spark Python3.8、真交通 state、完整 tokenizer 或真 Qwen 已通過本次新版本。

## Spark 下一道驗收（尚未執行）

新增 [accept_vehicle_id_labels.sh](../../validation/accept_vehicle_id_labels.sh)，由使用者手動執行。這不是重做 R6 同一 probe，而是**新實作**的 seed0/1 完整 prompt fixture、零 env.step、零真 Qwen call、零記憶讀寫，再用既有 Qwen 環境的本地 tokenizer 計算2048 context／256 output budget；不載入權重、不啟服務。fixture 回覆非交通政策，不可用作效果資料。

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
bash validation/accept_vehicle_id_labels.sh
```

所有新輸出/cache/tmp在 `/home/nclab/Yizhen/runs/M24-vehicle-id-*`，結尾列出確切 `review.tar.gz` 路徑。回傳該檔即可核對新標籤、所有初始車 ID、完整 messages、未步進及 token budget。[run_qwen_single_step](../../validation/run_qwen_single_step.py) 補記本次所有 simulator 變更來源 hash；沒有改其 traffic 執行方式。此工具仍使用既有 tokenizer 計數器，其歷史 limitation 字串提及 seed0，實際 seed 請依 fixture.seed 與各自路徑核對。

完整 memory-on 檢索候選與 token budget 仍需另作最小隔離驗收；這支 off fixture 腳本不驗證 memory-on。真 Qwen 最小驗收、任何正式批次皆未啟動；不要直接執行舊 resume 腳本。

## 配對比較與資料保留

1. 舊 M18 off（21799bd）對新命名 on：可列為不同軟體條件的描述性比較，不能宣稱純 memory 因果；交通 seed 相同不代表 prompt 或完整狀態軌跡相同。
2. M23 seed0 的396筆是舊命名 prompt 下的政策產物。即使記憶 stored text 多為空摘要，仍不可假設政策決策／metadata 不變。396庫續接新命名 seed1–19 會混合命名與版本，不能當同一版本的正式20seed on。
3. 建議研究設計：固定同一新 commit、模型 revision、環境、strict、參數、seeds0–19與既有終止／失敗規則；新 off 每seed獨立 episode，新 on 從全新空庫按seed順序累積。使用不同輸出目錄與全新庫，保留全部失敗，不自動重試。off 新基線包含 seed0，不能沿用舊M16 seed0。
4. on 跨 episode 學習使後面 seed 的 outcome 依賴前面 seed 歷史；可用同 seed 的配對描述，但不是20個獨立記憶處理樣本，推論與信賴區間須承認順序依賴。只重跑一兩個 off seed 可作 smoke，不能取代完整20seed新命名基線或證明其他seed不受影響。
5. 若目前只要排除命名崩潰而不做純 memory 效果主張，無須為保留舊觀測而重跑 off；先完成新版本驗收即可。是否投入全套新實驗留待使用者決定，這輪只完成實作與必要性評估。

原401庫、恢復396庫、兩次seed1失敗、R6證據及舊off均未動。既存 R4 刪除維持未提交，未restore，未納入此次commit。原作者副本未修改；無SSH、Spark操作或Windows模型載入。
