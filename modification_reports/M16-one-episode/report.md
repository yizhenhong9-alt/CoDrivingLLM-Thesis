# M16：正式入口一回合實測與逐筆回答審查

日期：2026-11-23。本項是實驗驗收紀錄，未修改模型呼叫、parser、prompt、安全公式、優先權或速度處理。

## 測試前狀態

M15 已證實正式入口三步／0.6 秒可執行，strict 15/15 通過，但沒有完整回合證據。本次將程式保護上限設為 300 步、3600 秒，仍只執行一回合，讓原環境自行回報 terminal；無自動重試。

## 證據來源

使用者在 Spark 執行後提供本地檔案；本地讀取 [外層 result.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/result.json)、[正式入口 result.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/result.json)、[traffic console](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic-console.txt)、[server console](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/server-console.txt) 與 101 份 step JSON。沒有在本地載入模型或重跑模擬。

執行 commit=21799bdc2abc3b85d1c8562e90827e8287eeaf3d，工作樹乾淨；模型為 Qwen/Qwen3-30B-A3B-Instruct-2507-FP8，seed=0、strict、memory off。traffic entry_point=Run_multi_CAV_LLM.py。

## 實測結果

| 項目 | 結果 |
|---|---|
| 外層／正式入口狀態 | project_episode_terminal／episode_terminal |
| 真正步數 | 101，step_id 0–100 |
| 實際物理更新 | 301 ticks，simulation_frequency=15，合計約 20.0667 秒 |
| Negotiation | 101 次回答，101 次 strict 成功 |
| Action | 404 次回答，404 次 strict 成功 |
| 合計 | 505/505，本回合樣本解析率 100%；無 no_text |
| 回答完整性 | 505 次 API finish_reason 均為 stop |
| CAV 碰撞 | 101 步的四台 CAV crashed 皆為 false |
| 最後 done | true；agents_dones=[true,true,true,true] |
| Memory | memory_module_imported=false |
| 停服 | exit_code=0、埠已關、已知程序無殘留、clean_observation=true |

最後一步提早 terminal，因此只有 1 個 physics tick，前 100 步各 3 ticks。不可直接用 101×0.2 推算實際模擬時間。console 搜尋未見 EngineDeadError、semaphore、force killing、ZMQError；不宣稱所有警告都不存在。

### 終止原因的判定與限制

最後記錄見 [step-0100.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0100.json)。四台 crashed 均為 false，info.cav_crashed=false、cost=0，四台 agents_dones 均為 true。

實際設定 duration=50、policy_frequency=5，原終止步數上限為 249（逐車上限 250），本次只到 101；offroad_terminal=false，也未到 CLI 300 步或程式超時。依目前原始 [IntersectionEnv 終止條件](../../highway_env/envs/intersection_env.py) 與 info，可推定四台皆符合原 has_arrived 出口條件，而非碰撞／時間到終止。

這是根據原方法與回傳資料的條件推論：目前 step 狀態未直接保存 lane_index、local_coordinates 或每台 has_arrived 的布林值，不能寫成已逐車重建並實測該值。has_arrived 定義是進入出口車道並前進一定距離，不等於到達任意自訂最終目的地。

## 原始回答確實如何變化

Negotiation 出現三種原文：

| 原文 | 次數 |
|---|---:|
| `{"decisions":[{"first_vehicle":4,"second_vehicle":3},{"first_vehicle":5,"second_vehicle":3}]}` | 40 |
| `{"decisions":[{"first_vehicle":5,"second_vehicle":3}]}` | 3 |
| `{"decisions":[]}` | 58 |

因此 101 次 negotiation 中，43 次有非空通行順序，58 次沒有列出的衝突配對。空 decisions 也是有效回答，但不能當作複雜衝突決策能力的證據。

Action 原文例如：

```json
{"vehicle_id":3,"decision":"SLOWER"}
```

每台車各回答 101 次，分布如下：

| 車號 | SLOWER | IDLE | FASTER |
|---|---:|---:|---:|
| 3 | 2 | 52 | 47 |
| 4 | 0 | 47 | 54 |
| 5 | 0 | 89 | 12 |
| 6 | 0 | 25 | 76 |

以上只是回答分布，不能只由加速／減速次數評價是否合理。IDLE 保留既有目標速度，並非瞬時車速保證；原提示前截速至 5 m/s 也仍不代表全程硬性限速。safety_guarantee=false 如原設定，不能宣稱本回合是 supervisor 強制保護的成果。

## 本地逐筆審查方法

使用目前專案 strict parser，對 101 份 step 中每個 raw_response 重新呼叫 parse_negotiation／parse_action，使用保存的 pairs、vehicle_id、available_actions；比對保存的 parser 值、動作 ID、提交車號順序與環境動作，另核對步數連續性、finish_reason 與 CAV crashed 旗標。未發現不一致。

審查數字、回答分布與 102 個輸入 JSON 的 SHA256 保存於 [audit.json](./audit.json)。這是使用同一 parser 的離線一致性檢查，不是第二個獨立交通決策判定器，也沒有重新產生 LLM 回答。

## 與修改前比較，以及下一步

相較 M15 三步接線驗證，本次已得到指定 Qwen 經正式主入口的一回合執行證據，並有 505 筆回覆的解析一致性資料。可以作為本次模型替換／整合後、seed 0 的基線實驗紀錄。

仍不能據此宣稱：所有 seed／場景 100% 可解析、比 GPT 更好、新 parser 比原版整體更好，或既有距離與速度問題均已修復。此回合沒有公平的原版對照；prompt、輸出格式與 parser 的變因需控制。

下一步建議先閱讀關鍵步驟的完整 prompt／回答，理解動作轉換與原場景敘述，之後才用少量不同 seed 檢查重現性。保持已知負距離、速度及優先權基線不變；若要修改，另編號並做前後比較。此回合已結束，不需為建立報告而重跑。

## 關鍵步驟導讀：prompt → 原文 → 車輛變化

以下 step_id 從 0 起算，所以 step-0000 是第一次決策。摘錄僅為閱讀方便，完整 prompt 保留在各 step JSON 的 calls[].messages[].content；raw_response 是真正模型輸出，parsers 是程式解析結果，environment_action 是環境記錄動作。模型未輸出理由，以下不能當作已知模型內部判斷過程。

### step_id 0：建議後通行，車 3 回答 SLOWER

見 [step-0000.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0000.json)。negotiation 收到配對 [[4,3],[5,3]]、車速與到衝突點距離，輸出車 4、5 各先於車 3。車 3 的 action prompt 同時包含同車道安全警告、建議後通行，以及可用動作 IDLE／FASTER／SLOWER。

模型原文為 `{"vehicle_id":3,"decision":"SLOWER"}`，解析為車 3、action ID 4，環境動作的車 3 位置也是 4。車速由 5 降至約 3.51 m/s。這個回答與提示的減速建議一致，但不能證明模型具體採用哪一段資訊作決定。

### step_id 1：多行 JSON 仍能解析，IDLE 仍可能持續減速

見 [step-0001.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0001.json)。車 3 當步可用動作只剩 IDLE／FASTER，模型實際輸出：

```json
{
  "vehicle_id": 3,
  "decision": "IDLE"
}
```

strict parser 正確處理換行與空白，解析為 ID 1；車速仍由約 3.51 降至 2.47 m/s。原控制器的 IDLE 不重新設定目標速度，所以不能把動作名稱直接解讀成瞬時車速完全不變。prompt 卻仍使用 `IDLE--remain in the current lane with current speed`，這是需要另行釐清的文字與執行語意差距，不是 parser 讀錯。

### step_id 35：仍有讓行建議，但危險資訊段落寫「沒有衝突」

見 [step-0035.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0035.json)。negotiation 仍列 [[4,3],[5,3]]，車 3 的 prompt 仍附兩條建議後通行；但同一 prompt 也寫：

```text
Acceleration conflict: acceleration is safe
Currently, ego vehicle do not have conflict
Conflict info is empty
```

車 3 此時已接近停止（步前約 0.0000213 m/s），回答 FASTER。這只能說實際輸入存在易混淆的敘述，不能將動作轉換直接歸因於某一句話，或因此判定其行為安全／不安全。

### step_id 42／43：配對消失後又出現

見 [step-0042.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0042.json) 與 [step-0043.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0043.json)。42 的輸入 pairs=[]，模型回答 decisions=[]，車 3 回答 FASTER；43 的輸入重新出現 [[5,3]]，模型回答 5 先於 3，車 3 回答 IDLE。

所以空清單與配對恢復先發生在程式產生的輸入，不是 parser 丟掉配對，也不是模型自行新增配對。為何偵測結果在相鄰步改變，需另外審查原 detect_conflicts 的條件與場景數值，不能僅由這兩份回答判斷是 bug。

43 的 action prompt 同樣同時寫「沒有衝突」和「與車 5 有衝突，建議後通行」。本次未修改此文字。

### step_id 100：環境結束，不是模型輸出停止命令

見 [step-0100.json](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe/step-0100.json)。模型只輸出四台車的正常動作，車 3 為 IDLE；執行後由原模擬環境回報 done=true，主迴圈才結束。不是模型直接決定關閉回合或服務。

### 導讀發現的優先事項

原 [check_safety_with_conflict_vehicles](../../llm_controller/prompt_llm.py) 只分析被建議後通行的車，按 TTCP（預估到衝突點的時間）差異分級，只有 level 高於目前危險等級時才填 most_dangerous_info。原 format_training_info 在沒有該資訊時卻輸出「沒有衝突」。因此「未選出危險項目」與「完全不存在衝突配對」可能被同一句話混用。這是由原程式路徑與保存 prompt 確認的文字問題；本次未逐筆重算 TTCP，未判定特定步究竟走哪一條數值條件。

下一項應先做離線審查：分清楚衝突配對、風險分級與通行建議，並核對 IDLE 及速度敘述。不更改安全公式、門檻、優先權或 5 m/s 處理。確認可接受的文字修正範圍後，再另編修改號碼與前後比較，避免把原 prompt 問題誤算成 parser 或 Qwen 的能力差異。
