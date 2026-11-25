# M17：離線 prompt 一致性審查

日期：2026-11-23。狀態：審查完成；具體文字修正範圍已提出，尚未套用正式 prompt。本項未改控制行為。

## 基線與範圍

完整閱讀正式入口交接、原部署交接（以文末 30B FP8 更正為準）、Qwen 替換計畫及 M16 報告。查無工作區及 repo 內適用 AGENTS.md，亦未發現 C:/AGENTS.md。分支 qwen-local，HEAD=a669568cfbe07fef08dbd44d2b353c78bdba027d，審查前工作樹乾淨。

使用 [M16 保存資料](../../../runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe) 的 101 份 step JSON；不重部署、不呼叫模型、不重跑模擬，不安裝套件。指定模型與 M16 執行版本以 [M16 報告](../M16-one-episode/report.md) 為準。

## 全回合離線觀察

[audit.json](./audit.json) 保存逐筆判定及 101 個輸入 SHA256；[audit.ps1](./audit.ps1) 為可重複執行的 PowerShell 審查工具。每筆 action 合併 messages，檢查原句與 first／second 建議是否共存，沒有推測模型理由。

| 項目 | 數量 |
|---|---:|
| step JSON | 101 |
| action prompts | 404 |
| 含「Currently, ego vehicle do not have conflict」 | 367 |
| 上述句子與通行建議同時出現 | 89 |
| 其中車 3／4／5 | 6／40／43 |
| 含 IDLE「remain in the current lane with current speed」 | 404 |

89 的單位是「一台車在一步的 prompt」，不是 89 個不同步數，也不是碰撞或模型答錯次數。計數涵蓋 passes first 與 passes second，不把兩者混為讓行。

車 3 的 step 35 有兩項配對、兩條後通行建議與無衝突句；step 42 為零配對、零建議；step 43 恢復一項配對、一條後通行建議，亦有無衝突句。這重現保存文字矛盾及輸入配對變化，未判定偵測邊界是否正確。

## 來源與語意

[check_safety_with_conflict_vehicles](../../llm_controller/prompt_llm.py#L614) 僅由原 regex 擷取 passes second 的對象；不是對全部偵測配對逐一評估。dangerous_level 初始為 0，只有 level 大於目前值才填 most_dangerous_info。原門檻依 abs(TTCP差) 為 >8、>5、>2、其餘四級；level=0 不填資訊。沒有匹配到後通行對象或沒有對應 conflict_group 也會留下空資訊，不能將這些情形一概說成「沒有配對」或「已確認安全」。

[format_training_info](../../llm_controller/prompt_llm.py#L686) 只看 delta ttcp 是否為 None，空值就輸出「沒有衝突／資訊為空」。因此存在兩個不同問題來源：先通行車的配對未進入本 helper 的後通行分析；後通行車亦可能未選出 level>0 項目。車 4、5 的大量案例不能僅用低風險解釋。本輪沒有重建場景或逐筆重算 TTCP，不宣稱車 3 特定步必然因 >8 門檻而進入空分支。

[動作描述](../../llm_controller/prompt_llm.py#L71) 使用 current speed。[MDPVehicle 與 ControlledVehicle](../../highway_env/vehicle/controller.py) 的 IDLE 路徑保留目標速度，實際速度仍由速度控制器更新。M16 step 1 車 3 回答 IDLE，速度仍約由 3.51 降至 2.47 m/s；這不是 parser 誤讀，也不代表模型輸出停車意圖。

## 具體文字修正範圍（提案，未套用）

1. 將空資訊的兩句合併為：`No most-dangerous conflict detail was selected by the current assessment. This does not mean there are no detected conflict pairs; refer to the negotiation advice separately.` 不聲稱無配對，不自行補造風險數值，也不修改既有 acceleration is safe 分級輸出。
2. IDLE 說明改為：`remain in the current lane without changing the target speed; actual speed may still change as the controller tracks that target`。只更正文義，不變更 action ID、可用動作、控制器或速度裁切。
3. 保留原 negotiation 建議句、regex、車號及配對順序；不可直接潤飾 passes second，否則可能破壞 helper 的字串擷取。若希望改善文法，需另保留供程式讀取的結構化來源後再處理。
4. 優先在 Qwen prompt 組裝邊界做有限文字替換，保留 legacy 基線；不要先改共用 ACTIONS_DESCRIPTION 或共用 formatter，避免未刻意控制就影響原版比較。實作時須確認替換命中範圍，而非全域刪改 conflict 或 safe。

## 後續修正的驗收條件

- 保留 M16 原始檔與雜湊，另存修改前後 prompt；逐筆確認只改上述兩處文字。
- 涵蓋零配對、先通行、後通行但未選出危險資訊、已有危險資訊的案例；有資訊段落原文應不變。
- 同一原始資料的配對、建議順序、風險計算／分級、可用動作與 action 映射完全一致；保留 legacy prompt 及兩種 parser。
- 以指定官方 tokenizer 及 chat template 重算正式 prompt 加輸出預算；不能以字元數或舊 2048 健檢代替。真模型效果須另有新證據，不能回寫為 M16 已驗證新文字。

## 已完成檢查與限制

已離線掃描完整 101 步／404 份 action prompt，並核對 step 35、42、43 的車 3 明細；審查結果可由保存 JSON 重現。PowerShell 預設不允許直接執行 ps1，本次將相同腳本文字作為 scriptblock 執行，未修改系統執行原則；輸出路徑明確指定此報告目錄。

本項僅新增審查工具、結果、報告與索引；正式 prompt、安全公式、風險門檻、優先權、signed distance、5 m/s 裁切、parser、memory 路徑均未改。未重新解析 505 筆回答（沿用 M16 審查證據），未驗證新 prompt token 或模型效果，未判定配對短暫消失的數值原因，亦未處理原 helper 中其他可疑欄位。
