# M18：intersection、20 seeds、memory off 實驗審查

審查日期：2026-11-24。本項只有離線資料審查與報告，未改控制程式、prompt、parser、安全公式、門檻、優先權、速度處理或記憶功能，沒有重跑任何回合。

## 資料與版本

seeds 1–19 來自 [M18 原始結果](../../../runs/M18-intersection-memory-off-20seeds/)；seed 0 沿用 [M16](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/)，不是本批重跑。每個 seed 恰有一份外層及一份 traffic 回合結果，未將早先另存的 seed 1／17 副本重複計入。

20 回合皆記錄 git_commit=21799bdc2abc3b85d1c8562e90827e8287eeaf3d、工作樹乾淨；保存的 llm_controller 各檔與正式主入口 SHA256 相同，完整 config 相同。模型 Qwen/Qwen3-30B-A3B-Instruct-2507-FP8，strict、memory off、memory_module_imported=false、safety_guarantee=false；max_steps=300、wall_seconds=3600。config.seed 固定為 0 不等於每次使用 seed 0：正式入口以 args.seed 傳入 reset(is_training=False, testing_seeds=...)，原 reset 依 testing_seeds 設定 NumPy 與 random。

## 成功定義與結果

本報告將成功定義為「本回合全程未記錄 CAV 碰撞，且依原終止條件推定四台 CAV 都達到出口條件」。不是只看 episode_terminal，也不是只看 parser。

| 指標 | 分子／分母 | 比例 |
|---|---:|---:|
| 無 CAV 碰撞且推定全車達出口 | 9/20 | 45% |
| 曾有 CAV 碰撞的回合 | 7/20 | 35% |
| 無 CAV 碰撞、到環境時間上限仍未全車到達 | 4/20 | 20% |
| 全程未記錄 CAV 碰撞 | 13/20 | 65% |
| 程式執行至環境 terminal | 20/20 | 100% |
| 保存紀錄中 strict 解析成功 | 11625/11625 | 100% |
| 停服檢查 clean_observation=true | 19/20 | 95% |

共 2325 個決策步，negotiation 2325 次、action 9300 次；6954 physics ticks，模擬時間合計約 463.6 秒。所有保存 API finish_reason 均為 stop。這些百分比只描述本次固定 seeds 0–19，不能推論其他 seed／場景或優於原模型。

## 各 seed 結果

| seed | 步數 | 結果 | 停服警告 |
|---:|---:|---|---|
| 0 | 101 | 推定全車達出口 | 無指定警告 |
| 1 | 107 | 推定全車達出口 | 無指定警告 |
| 2 | 45 | CAV 碰撞 | 無指定警告 |
| 3 | 249 | 環境時間上限 | 無指定警告 |
| 4 | 46 | CAV 碰撞 | 無指定警告 |
| 5 | 100 | 推定全車達出口 | 無指定警告 |
| 6 | 83 | 推定全車達出口 | 無指定警告 |
| 7 | 249 | 環境時間上限 | 無指定警告 |
| 8 | 249 | 環境時間上限 | 無指定警告 |
| 9 | 187 | CAV 碰撞 | 無指定警告 |
| 10 | 105 | 推定全車達出口 | 無指定警告 |
| 11 | 110 | 推定全車達出口 | 無指定警告 |
| 12 | 72 | 推定全車達出口 | 無指定警告 |
| 13 | 97 | 推定全車達出口 | 無指定警告 |
| 14 | 54 | CAV 碰撞 | 無指定警告 |
| 15 | 64 | CAV 碰撞 | 無指定警告 |
| 16 | 34 | CAV 碰撞 | 無指定警告 |
| 17 | 82 | 推定全車達出口 | EngineDeadError |
| 18 | 249 | 環境時間上限 | 無指定警告 |
| 19 | 42 | CAV 碰撞 | 無指定警告 |

## 判定依據

逐步核對 initial_vehicles／final_vehicles 的 crashed 及 info.cav_crashed。成功的 9 回合皆在環境時間門檻前終止、末步 done=true、四台 agents_dones=true、全程 CAV crashed=false、offroad_terminal=false。依原 IntersectionEnv._is_terminal／_agent_is_terminal 條件排除碰撞、時間與離路原因，推定全車達出口。

限制：尚未直接保存 lane_index、local_coordinates、has_arrived 布林，所以是依條件推定，不是逐車重建出口位置。無碰撞率只涵蓋受控 CAV，不代表背景車完全沒有碰撞。

seeds 3、7、8、18 均在第 249 步回報 done=true；末步 agents_dones 全 false、cost=0、無 CAV 碰撞。符合 duration=50、policy_frequency=5 所形成的原門檻 249；不是 CLI 的 300 步上限。這四回合不計成功，也不因 terminal 而計為到達。

## 解析與資料一致性檢查

[audit.ps1](./audit.ps1) 逐筆掃描 2325 份 step，核對數量／步號、完成狀態、保存的 strict 狀態、raw_response 與 API content、action 原文車號／動作與解析值、當步可用動作、提交及環境動作，未發現已執行檢查的不一致。保存的輸入檔 SHA256 與逐 seed 統計見 [audit.json](./audit.json)，可讀表見 [summary.csv](./summary.csv)。

本次未重新呼叫專案 strict parser，也未用獨立交通判定器分析動作安全；100% 為保存的解析狀態及本次一致性核對結果。source_sha256 只涵蓋紀錄列出的控制模組與主入口，不能當作整個 repo 所有檔案的完整雜湊驗證。

## 異常保留

seed 17：回合 82 步、410 次 strict 全成功、推定全車達出口；停服 exit 0、埠已關、已知程序無殘留，但 shutdown 期間記錄 EngineDeadError，外層保留 needs_shutdown_review／clean_observation=false。此回合的交通成功與停服品質分開統計，不重跑或刪除異常。

seeds 1、11、17 的 traffic console 出現 divide by zero 警告，來源為原安全 helper 的 distance / relativeSpeed。本輪未重算這些數值或評估其決策影響，不擅自修公式或把警告視為無影響；列為後續離線調查事項。

## 後續使用

本組可作為目前 Qwen strict、memory off 的基線。後續 memory on 或 prompt 變更需各自編號並控制其他設定，不能將成功率差異直接歸因於單一因素。M17 文字提案仍未套用。
