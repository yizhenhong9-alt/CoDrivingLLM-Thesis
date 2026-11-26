# M24-R4：prompt／memory 原始程式對照與404筆續跑工具

2026-11-27。使用者同意接續保留M24 seed0並從副本跑1–19，同時詢問是否僅改MDPVehicle，其餘文字／格式皆依原始論文。

## 精確回答：要分比較基準

相對M24之前的Qwen版本：M24修改所有Vehicle的字串身份（MDPVehicle、IDMVehicle都包含），改用vehicle.id，同時補copy／spawn身份承接與版本診斷。negotiation／action的prompt組裝及memory模板未在本次命名修正中改動。但實際prompt裡的車名會變，Qwen回覆與後續物理軌跡可能改變，因此不能說整個episode的其他文字／數值不變。

相對原作者程式：不是只有車名不同。現行Qwen版本在M24之前即有strict輸出、身份映射、外層prompt組裝、模型與embedding等改動。以下對照本機原作者副本（只讀，未修改），不是宣稱已完成論文逐條符合性審查。論文規範與作者程式不能直接當作同一件事。

| 層次 | 原作者程式 | 目前Qwen strict版本 |
|---|---|---|
| 模型 | send_to_chatgpt指定gpt-4o-mini | 本地固定revision Qwen3-30B-A3B-Instruct-2507-FP8 |
| request外層 | messages中一筆system，content為組裝文字 | 同樣一筆system，但content外層文字並非逐字相同 |
| negotiation場景 | traffic police角色、成對車輛／速度／距衝突點 | 同樣資料與原conflict偵測；外層換行、標點與輸出指示有差異 |
| negotiation輸出 | Final Answer，first_vehicle／second_vehicle為車輛文字標籤 | 只回JSON、整數simulation ID，新增Mapping與Pairs；之後轉回同一文字bridge給原helper |
| action核心場景 | prompt_engineer產生工具／車道／附近車輛／安全與摘要 | 直接使用同一方法，未重新設計安全評分或改用M17 |
| action外層 | 原較長敘述、原段落標題、Final Answer decision格式 | Current scenario／Rules／Attention points等較短標題；ChatGPT身份句改為driving assistant；只回vehicle_id與decision的JSON；加入simulation ID與available actions |
| action規則／注意事項 | PRE_DEF_PROMPT的intersection文字 | 保留同一規則／注意事項內容；不是說外層prompt逐字相同 |
| 車名 | MDPVehicle／IDMVehicle #Python位址餘數 | 同類別字樣 #正式vehicle.id，repr及所有str使用者一致 |

可核對的來源：[qwen_step](../../llm_controller/qwen_step.py)、[原agent action方法](../../llm_controller/llm_agent_action.py)、[原agent negotiation方法](../../llm_controller/llm_agent_negotiation_system.py)、[規則及工具](../../llm_controller/prompt_llm.py)。

### 原方法本次逐項AST對照

實際讀取 `C:/master's thesis/CoDrivingLLM` 三個對應來源檔，與工作repo比較AST（忽略註解／空白），13項全相等：

- action：prompt_engineer、memory_update、relative_memory、transfer_negotiation_prompts_to_results。
- negotiation：detect_conflicts、is_conflict、record_route_xy、get_lane_xy。
- prompt工具：PRE_DEF_PROMPT、cal_ttcp、check_safety_with_conflict_vehicles、generate_comment、format_training_info。

檔案SHA256與方法行號見 [R4-original-method-comparison.json](./R4-original-method-comparison.json)。這證明這13項原方法未被重寫，**不證明外層Qwen prompt與原作者send_to_chatgpt完全一致**，更不證明整個系統逐字符合論文。

### strict回覆的具體例子

negotiation目前要求：`{"decisions":[{"first_vehicle":4,"second_vehicle":3}]}`，不是原字串`"MDPVehicle #..."`的Final Answer。action目前要求：`{"vehicle_id":3,"decision":"IDLE"}`，不是原`Final Answer: "decision": {"IDLE"}`片段格式。strict是原M05以來已存在的接線選擇，不是這次M24新加。

## memory：保留的語義與不同之處

- query仍是scenario/prompt_info去空白後最後兩行以newline接起；stored text仍只有最後一行摘要，不是完整prompt／完整協商。
- 原四個metadata欄位保留：human_question='None'、negotiation_result='None'、final_action='[action_id]'、comments=原generate_comment。comments是決策前heuristic，不是step後交通結果評分。
- 給Qwen的經驗句保留 `- Last time {negotiation_result}, you choose to {final_action}, it is {comments}` 及原結尾；不是把stored text完整貼給Qwen，也不新增M17建議。此例中的negotiation_result通常是字串None，不是完整當前協商。
- 原作者action程式的retrieve呼叫與memory update呼叫原本被註解。現行on恢復原方法的retrieve→回答→write→下一車，四車後step；同一步後車可讀前車尚未step的寫入，跨episode累積。不能說作者原提交本來就在執行這個memory實驗。
- 原OpenAIEmbeddings改成固定revision的本地MiniLM，經loopback memory服務接Chroma；向量與檢索候選不保證相同。top_k=2，沒有另加相似度cutoff、成功篩選、去重或空摘要排除。
- 加source provenance／snapshot／write receipt／token檢查等實驗紀錄；source欄位不注入經驗句。超過2048context（保留256output）會整筆移除低排序候選2→1→0，base仍超則拒絕，不截斷原全文。這是目前實作限制，不是原作者prompt原生機制。
- 本輪續跑工具保留seed0原test_only=true全部metadata；seeds1–19新寫入test_only=false，報告明列來源差異。**這輪沒有再改決策prompt、memory經驗句、安全公式或速度**。

來源：[original_memory](../../llm_controller/original_memory.py)、[memory_prompt](../../llm_controller/memory_prompt.py)、原作者副本的memory.py（OpenAIEmbeddings）。

## 新增404筆續跑能力與保護

[retain_m24_seed0.py](../../validation/retain_m24_seed0.py) 僅接受已審查seed0全部回傳證據SHA256、101步、404個不同ID、確切snapshot及來源commit239a581。重新執行原validate_episode與M24身份檢查。不接受舊M23資料或任意新pilot。

準備階段只hash／copy原test-chroma，不在原庫開Chroma。來源有writer.lock即停止，不自動刪lock。新run與原run必須互不包含且目的不存在；copy後檔案hash一致，僅在副本開Chroma，核對全部404 ID／text／metadata及含向量的logical snapshot。不add/delete、不改source、不重算embedding。前後來源hash一致才ready。

初始與續跑前檢查git：highway_env、llm_controller、正式入口、Qwen manager、memory服務與原episode驗收實作，相對seed0 commit不得有差異。新commit只允許這次調度／驗收／報告等變更；未宣稱整份repo逐byte相同。

[run_memory_on_20seeds](../../validation/run_memory_on_20seeds.py) 新增互斥的--retained-m24-source，不改舊--recovery-source邊界。保留seed0 row與原來源資訊，initial_count404且snapshot精確匹配後跑1→19。每seed新寫入用false且依原validate_episode驗證；任一失敗停止並保留已寫入資料，不自動重試，M24已有batch-result時拒絕覆蓋。正常每seed結束也檢查M24名稱與CAV類別對應。

白名單collector支援M24與保留seed0證據，匯出SHA256清單與目錄外tar.gz，排除所有DB／cache。沒有HNSW邊界tie必然相同的保證；copy前檔案一致、copy開啟後logical snapshot一致是實際驗證範圍。

## 驗證與手動操作

本地11項新測試通過（含錯count／snapshot／ID／text／metadata／shape拒絕、證據篡改拒絕、source changed拒絕、只開副本且source hash不變、混合provenance、首seed從404起且失敗只呼叫一次並關閉service、白名單）；舊batch3、recovery4、episode3項通過，合計21項。另直接讀真回傳證據，404筆驗證PASS，決策程式與seed0無差異PASS；兩份shell bash -n通過。測試建置初版漏模擬Python3.8／把測試repo放在OWNER本身，已修正測試替身後重跑；不曾執行Spark交通。

先由使用者手動執行 [prepare_m24_memory_continuation.sh](../../validation/prepare_m24_memory_continuation.sh)。只準備副本，**不啟動Qwen、traffic或embedding模型**，全部新檔位於/home/nclab/Yizhen。回傳輸出的M24-review-*.tar.gz，確認Spark真副本ready後，再以實際prepared run路徑啟動 [resume_m24_memory_on.sh](../../validation/resume_m24_memory_on.sh)。尚未做Spark副本驗證，也未啟動1–19。

本序列必須表述為「保留已驗證M24 seed0＋後續1–19」，不是20seed全部最初即正式標記、不是純memory因果，也不是舊M23恢復。舊off、401／396失敗資料、原404庫全部保留；R4-label-collision-audit.md既存刪除不納入commit；原作者副本只讀。
