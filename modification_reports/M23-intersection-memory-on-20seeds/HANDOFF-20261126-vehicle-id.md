# 聊天詳細總結與新聊天交接：vehicle.id 命名與 off 基線可比較性

更新：2026-11-26。使用者明確要求詳細總結並開新聊天，起點為「將車號改成vehicle.id，評估是否須重跑intersection memory off 20 seeds」。這是新聊天的工作授權；先查證與實作可檢查版本，不能直接啟動Spark／重跑20seeds。

## 1. 工作區、Git與操作限制

- 工作區 `C:/master's thesis`，repo `C:/master's thesis/CoDrivingLLM-Thesis`，branch qwen-local，origin https://github.com/yizhenhong9-alt/CoDrivingLLM-Thesis.git 。本交接前HEAD為4c7898d3a390533b6f59d298db14c14badadd30a，已push。
- 每條Git命令必須 `git -c "safe.directory=C:/master's thesis/CoDrivingLLM-Thesis" ...`；不改全域設定。使用者已授權local commit／push。sandbox push常網路拒絕，依規範require_escalated重試。
- 原作者副本 `C:/master's thesis/CoDrivingLLM` 不可修改。新聊天先讀AGENTS並查git；本聊天未找到workspace／repo內AGENTS。不要自行委派subagent。
- 未提交刪除：`modification_reports/M23-intersection-memory-on-20seeds/R4-label-collision-audit.md`。在01247ad已提交，但檔案目前被刪，來源不明；原樣保留，不能restore或把刪除混進commit。R5、R6是另寫報告。
- 所有Spark操作由使用者手動；不可SSH、不在Windows載入／下載模型、不用雲端embedding、不重新部署Qwen。Spark新增檔案／結果／環境／cache只能 `/home/nclab/Yizhen`，不新增非必要套件。
- 不套M17 prompt文字提案，不改安全公式、門檻、優先權、signed distance、速度處理。命名改動需獨立編號與測試，不能宣稱只換embedding或決策必然改善。
- 既有off20seeds保留。最新要求是評估命名改後是否「需要」重跑，不是已授權直接重跑；如認為需做新基線，具體說明理由與範圍，保留舊結果。
- 繁體中文回覆，工具前commentary，工作區檔案引用用絕對Markdown路徑。Windows Python stdlib測試前configurePythonEnvironment/getPythonExecutableCommand；現有interpreter `C:/Users/user/miniconda3/python.exe` 3.13.13，PYTHONDONTWRITEBYTECODE=1。不把Windows替身測試稱Spark真驗證。

## 2. 原版 memory 語義與本地實作

原作者retrieval／update呼叫原本被註解。現在恢復其預留順序，而不是聲稱原提交原本已在運行記憶。

- query：`'\n'.join(prompt_info.strip().split('\n')[-2:])`，本次實際多為前導newline＋摘要。
- stored text：`prompt_info.strip().split('\n')[-1]`；不是完整場景、車道、安全評估、所有衝突對與協商文字。
- k2，無similarity cutoff、成功篩選、去重或空摘要排除。
- 原metadata四欄：human_question='None'、negotiation_result='None'、final_action='[id]'、comments=原generate_comment。extra source隔離標記來源，非prompt改善。
- generate_comment是根據離散到達關係與動作的固定heuristic，非LLM評分、非step後觀察。空摘要一律recommended to FASTER，即使選IDLE也如此。
- 每車retrieve→LLM回答→立即write→下一車；全車完成後env.step。同一步後車可讀前車尚未執行的決策。跨episode共用庫。
- 檢索用text向量；給Qwen的經驗句只呈現 `Last time {negotiation_result}, you choose to {final_action}, it is {comments}`，未附stored text。
- 正式CLI只 `--memory off/on`、預設off；on=原版檢索＋逐車寫入。使用者拒絕新增正式--memory-write／readonly實驗。歷史readonly僅是隔離驗收工具。

核心：local_memory.py stdlib manifest/vector/reference store；chroma_memory.py明確embedding_function=None、重複ID拒絕／寫後核對；memory_http.py loopback client；original_memory.py原版update捕捉與rolling count/snapshot；memory_prompt.py原格式與完整message token budget；qwen_step.py／qwen_episode.py正式接線。memory服務單程序encode→Chroma，sim3.8僅HTTP stdlib，memory3.12執行ML。

## 3. Spark固定環境

- repo `/home/nclab/Yizhen/src/CoDrivingLLM-Thesis`。
- sim `/home/nclab/Yizhen/envs/codriving-sim-py38` Python3.8.20，不改。
- Qwen `/home/nclab/Yizhen/envs/qwen-vllm034-py312`，Qwen3-30B-A3B-Instruct-2507-FP8，revision5a5a776300a41aaa681dd7ff0106608ef2bc90db，本地目錄models/Qwen3-30B-A3B-Instruct-2507-FP8-5a5a776300a4，API18080。
- memory `/home/nclab/Yizhen/envs/memory-chroma0415-py312` Python3.12.3 ARM64，Chroma0.4.15、numpy1.26.4、hnsw0.7.3、torch2.9.1+cpu、transformers5.22.2、safetensors0.8.0，R5固定89套件基線，不隨意升級。
- MiniLM all-MiniLM-L6-v2 revision717413c64de70e37b55cf53c9cdff0e2d331fac3，本地models/all-MiniLM-L6-v2/<revision>；原bin SHA c3a85f238711653950f6a79ece63eb0ea93d76f6a6284be04019c53733baf256，CPU weights_only轉safetensors SHA53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db，104 tensors。原證據以R6console為準。
- memory HTTP18082含CPU encoder與本地Qwen tokenizer／count；不另外疊embedding服務。2048context／256 output reservation，超額時整筆移除末位記憶2→1→0，base仍超則拒絕，不截斷全文。
- 既有Qwen manager GPUutil0.40、KV536870912、Triton、eager、maxseq1、batchtokens256，parent-only SIGTERM等120秒＋觀察；不killpg／SIGKILL。memory child SIGINT等30秒，不強殺。

## 4. 已完成驗收與資料

完整歷史報告見M20／M21／M22，以下是本聊天重要里程碑。

| 階段 | 已核對結果 | 本地回傳資料 |
|---|---|---|
| M20-R7 | Python3.8→3.12 memory HTTP create/reopen PASS，兩筆原模板 | 早期console／R7報告 |
| M21-R1 | 404 action tokenizer replay，max1129 | runs/m21-1 |
| M21-R2 | 真MiniLM／Chroma→prompt，兩案例1129／949 | runs/m21-r2 |
| M21-R3 | 兩份凍結真檢索prompt→真Qwen，無step | runs/m21-r3 |
| M21-R4 | 即時readonly四query、五fixture、0step | runs/m21-r4 |
| M22-R1 | 原版mutable on，空庫兩scope，query前庫0..7、8writes、0step | runs/m22-r1 |
| M22-R2 | 真Qwen五calls、4writes、1step、無CAV碰撞，manager補件完整 | runs/m22-r2 |
| M22-R3 | seed0完整99steps、396writes、495calls、19.8模擬秒，推論四車到達、停服乾淨 | runs/M22-R3-review-vWvyDf |

M22-R3 SHA256清單112檔核對，最大input1093＋256=1349，無候選排除。357/396（90.15%）stored text為Conflict info is empty、只有18種text。789個候選有17個來自同一步較早車寫入。沒有因果效果結論。

原空摘要原因：check_safety_with_conflict_vehicles只分析建議ego passes second者，dangerous_level從0開始，只有level>current才填most_dangerous_info。若沒有匹配或abs(delta TTCP)>8全部level0，delta仍None，format_training_info就輸出「ego do not have conflict／Conflict info is empty」。此文字不等同整場景無危險。357筆空摘要中355筆prompt無passes second，2筆有；step35車3有協商衝突但摘要空，未保存內部TTCP故不能斷言是哪個條件。

TTCP cal_ttcp以距離、速度、速限與加速度2估算到衝突點時間；delta=other−ego。路徑潛在衝突與TTCP嚴重程度是不同層：negotiation.detect_conflicts/is_conflict用route幾何採樣、不同lane、路徑距離<1m、兩車至衝突點<50m及目的地直線距離近似前方判斷；此層不使用TTCP。不可改這些公式或門檻。

## 5. M18 memory off基線

原commit21799bdc2abc3b85d1c8562e90827e8287eeaf3d，seeds0–19；seed0沿M16，1–19為M18。strict、memoryoff、相同config、300steps／3600s。

9/20無CAV碰撞且推論全車到達、7/20CAV碰撞、4/20環境時間上限（249步），共2325steps／11625calls。seed17停服EngineDeadError保留，不重跑洗掉。seeds1/11/17原安全helper divide-by-zero警告保留。

本地原始資料：runs/M18-intersection-memory-off-20seeds；seed0 runs/M16-one-episode/20261123T091604Z-c6871ba4。M18/report.md、audit.json、summary.csv已存在。baseline contract validation/memory_on_baseline_contract.json由M16原結果擷取，不能把config.seed0誤解為每個reset都是seed0。

## 6. M23首次失敗：Chroma回傳超額候選

正式batch原授權seeds0→19，共用全新累積庫；已完成off不重跑。runner validation/run_memory_on_20seeds.py/.sh，collector白名單排除DB／cache，batch異常停止不自動重試。

原Sparkrun `/home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-Y6aiqi`，commit efc8a01d0196c90a77424e47952a3c10a3f94002；回傳runs/M23-review-n2o60wtb，121檔hash通過。

- seed0完成99steps、396writes，這次實際simulated_seconds=19.733333（不能直接用99×.2取代觀測ticks），到達推定通過。
- seed1原第一次：完成step0四寫入＋一次step；step1車3再寫一筆，車4retrieve HTTP400，第二次env.step未執行。庫401筆，session正常close，snapshot4cf387ba43dbc389452665f8fc369118cb11778d1eee64602f4c69a5ef4c8e46。
- Qwen停服clean，錯誤不是已證明的斷線／OOM。舊HTTP錯誤只留泛用類別、未留詳細cause，且失敗query在prepare前未存，誠實承認診斷不足。
- 隔離副本diagnose_memory_retrieval.py（只新副本開Chroma，原檔前後hash）R1回傳runs/M23-R1-retrieval-diagnosis-uN3gb8：19probe中1失敗。requested2，四欄皆回3，distance有效，adapter恰好等長2的guard拒絕，映400。支持原因鏈，但不是精確失敗query重播；未知為何Chroma超額，不把tie當已證明根因。
- b033cea修正：一致欄長且size≤returned≤count，驗證全部ID/text/meta/distance後既有score/ID排序再cap2。不可吞錯成空候選、不可放寬安全公式。R2回傳runs/M23-R2-retrieval-check-jisokB：19/19 PASS，原超額probe仍3筆但final2，原401庫及副本邏輯快照不變。

## 7. M23恢復與第二次seed1失敗

add6a861bebebe122fd684ed8578e093d8593103新增recover_memory_batch.py、resume_memory_on_20seeds.sh、check_memory_recovery.py及batch／collector recovery支援。

恢復方案：原401庫不開Chroma只hash/copy；新副本檢查401ID集合、snapshot，精確刪除失敗5ID，要求恢復396與seed0 snapshot80b2410d97db53a97a72e59d893c634ca7f6d2463eb83e63f88175266db9d31c。保留seed0及原失敗attempt，resume1–19，明確版本差異與seed1retry標籤。不聲稱HNSW實體索引位元級還原；刪除後logicalsnapshot一致不保證tie邊界完全不受index影響。

Spark恢復run `/home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-recovery-EBUWXS`；launcher `/home/nclab/Yizhen/runs/M23-resume-launch-RcQEJx`，當時PID2133478（現在不能當作仍活躍或拿來kill）。以nohup執行、不需新套件；tail -f只等待log，Ctrl+C不會停止背景程式。

回傳runs/M23-review-6so9070d與runs/M23-resume-launch-RcQEJx。恢復READY、原401庫未動、新副本396。seed1第二次在step0 guard報 `Original safety-helper labels collided`，calls=[]、0step、0query、0write，final396與初始snapshot一致。Qwen曾啟動但沒交通決策，正常停服。seeds2–19從未啟動，批次已停止，不是背景仍跑。

原始401庫、恢復396庫、兩次seed1失敗資料全保留。目前**沒有完成19seed續跑，也沒有完成20seed memory-on結果**。

## 8. 車名碰撞：已證明的來源與實例

原作者highway_env/vehicle/kinematics.py:262 Vehicle.__str__：

```python
return "{} #{}: {}".format(self.__class__.__name__, id(self) % 1000, self.position)
```

這是顯示文字標籤，不是正式vehicle.id。%1000取餘數，不保證唯一。可能原意是縮短除錯顯示，但沒有作者動機證據，不能當事實。改%10000也不保證唯一／穩定。

唯一性guard qwen_step.py在M05早期65a4d99已加入，off21799與onadd6a86都存在。**命名來自原作者；guard來自我們較早Qwen接線**，不要混稱都是原作者功能。

R5 audit_label_history.py／label-history-audit.json核對七個來源blob在off／on逐byte一致：kinematics、abstract、intersection_env、llm_agent_action、llm_agent_negotiation_system、prompt_llm、vehicle_actions。offseed1的107step全部已保存名稱唯一；off與兩次on四台CAV初始位置／速度／crashed完全相同（不等於已證明所有HDV／內部狀態相同）。off車3 #640、第一次on #520，同交通seed不固定Python id。memoryon新增import／物件可能間接影響配置，但未證明是哪個allocation造成collision。

75c7072新增碰撞前持久保存vehicle_identifiers與legacy_label_collisions（simulation_id、python_object_id、modulo_1000），保留原guard；probe_vehicle_labels.sh只seed1fixture零步進，不啟動真Qwen／memory，不改原庫。不是精確memoryon配置重播。

**使用者已執行R6，不要再說尚未執行。** Spark `/home/nclab/Yizhen/runs/M23-R6-label-probe-OrT4ih`，本地runs/M23-R6-label-probe-OrT4ih，capture20261126T072139Z-dc96e77e.json：

| simulation_id | Python object id | %1000 | label |
|---:|---:|---:|---|
| 3 | 275988742030624 | 624 | MDPVehicle #624 |
| 6 | 275988742848624 | 624 | MDPVehicle #624 |

兩數不同，正式3/6不同，但原字串同名。其餘road labels IDM#96/#264/#768、MDP#720/#464。calls=[]、0step，失敗是guard正常拒絕。此為直接實際證據，但不能回推上一失敗的重複者也是同兩車。4c7898d補記此結果。

## 9. 新聊天應執行的下一步

使用者最後明確指定：「起點為將車號改成vehicle.id的方式，並評估是否須重跑intersection memory off 20 seeds」。不要只再解釋已知餘數問題；先核對AGENTS/Git並保留R4未提交刪除，讀本交接與R5/R6，開始具體查證／實作／測試。

1. 全面追查vehicle.id分配與重置、HDV/CAV、spawn／replacement／深copy，確認唯一性及生命週期。已存在EpisodeVehicleMap是動作層身份保護，不等於所有顯示字串自動使用它。不可只改Qwen names；原helper透過str(vehicle).split(':')[0]、regex匹配找車，整條鏈必須一致。
2. 評估最小且可隔離的唯一命名方式。使用vehicle.id而非id(self)%1000是授權方向；若需要適用範圍guard或明確啟用方式，保留原off基線可重現性。不要悄悄修改正式id或重排車輛。
3. 新編號（例如M24或M23-R7，依repo目前命名決定）留下變更、資料／prompt變化及測試。維持class字樣與現有regex可解析形式，驗證同一物理state／指定order的安全計算結果保持一致，碰撞案例能唯一找對車；名稱guard仍應保留。
4. 本地用stdlib/AST／替身做意味明確測試；Spark先零步進命名／完整prompt／token驗證，再視需要最小真Qwen驗收。不可直接跑新的20seeds。
5. 舊off20seeds仍是有效舊命名結果，但新on加了命名變更，不可把差異全歸因memory。必須獨立評估：若研究要嚴格隔離memory，是否需「新命名off基線」；若只描述舊off vs恢復後on，應明列混雜與版本，不能宣稱純memory因果。使用者先前禁重跑，最新要求只授權評估是否需要；不要未說明就自動跑。原20seeds不能覆蓋／刪除，也不要用反覆換seed／重試挑結果。
6. 新命名會改prompt文字與token，Qwen可能改回答／變好或變差，不能保證決策不變。純標籤改動與安全數值不變需用測試支持；評估應用到保留seed0／後續1–19時版本混合是否還適合作為正式實驗，必要時先提出清楚可檢查的方案。
7. 恢復工具目前只支援最初Y6aiqi401→396邊界，不泛用其他中斷點。不直接重啟舊resume；新命名驗收前正式批次保持停止。

## 10. 最近版本索引

- efc8a01：正式20seed批次，初次seed1 retrieve400。
- b033cea：Chroma超額候選相容修正，Spark副本19probe已PASS。
- add6a86：新副本恢復396並續跑1–19，seed1在label guard零步停止。
- 01247ad：標籤失敗審查；R4檔案目前未提交刪除，保留。
- 78c14d0：off/on來源與label歷史審查。
- 75c7072：碰撞前診斷保存＋seed1零步probe，18項本地測試PASS。
- 4c7898d：Spark車3與6實例證據報告。

完整逐項測試數、來源與限制見各report。本交接是對話索引，不取代原始JSON。新聊天可讀取資料，但不要重新下載或載入模型。所有手動指令須給出實際可用路徑，避免未說明的「實際編號」被使用者原樣貼上；長批次提供nohup及具體log位置、完整review匯出，不用tmux安裝。
