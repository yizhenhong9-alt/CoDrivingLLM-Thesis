# M22-R1：依原版逐車檢索／步前更新，正式 CLI 只分 off／on

## Spark 回傳審查（2026-11-25）

測試 commit `d9abe48b0b3d63bf6164e70386be638fbb1df779`；使用者 console PASS／exit 0，結果 `/home/nclab/Yizhen/runs/M22-R1-original-memory-GuYu06`。已核對 acceptance、config、commit 及兩份 capture；[離線審查程式](./audit_spark.py) 通過，[spark-audit.json](./spark-audit.json) 保存數值與回傳檔 SHA256。以下歷史待驗敘述以本補記更新。

- 第一 scope 查詢前庫筆數 0／1／2／3，候選 0／1／2／2；第二 scope 庫筆數 4／5／6／7，候選均 2。八個唯一 ID 均有 verified 寫入 receipt，最後 8 筆。
- 所有候選 ID、文字與 metadata 對應較早寫入；receipt 文字／metadata hash、manifest、query／prompt hash、source commit／scope／step／vehicle 一致。逐車快照鏈連續，第二 scope 初始快照等於第一 scope 最終快照。這是回傳 JSON receipts 交叉核對，未另行開啟 Spark DB。
- 原四欄 None／None／[action_id] 與空衝突既有 heuristic 評語保留；source 標記 test_only=true，沒有將 fixture 當作實際結果。每個 session 四查詢／四寫入／九次 token checks，正常關閉且最終 snapshot 驗證通過。
- 十份完整 prompt 最大輸入 1107 tokens；加預留輸出 256 為 1363 ≤ 2048，八次檢索沒有因長度排除候選。
- 兩個 scope 均為 fixture、零真正 Qwen 呼叫、零 env.step；不是兩個完整 episode，亦不是正式 memory-on seeds／交通安全效果驗證。下一階段可準備最小真正 Qwen＋memory-on 步進聯測，正式預設 off 不變。

2026-11-25。使用者明確選擇依原版，不將「唯讀檢索」另作正式實驗。現已實作 on=檢索＋每車回答後寫入、主入口 CLI 與每回合共用 session；本地替身測試通過，Spark 空庫／跨scope讀寫仍待手動驗收。沒有自動執行真Qwen或交通實驗。

## 先釐清原版與本次授權

原作者原始碼的 retrieval／update 呼叫目前都是註解；此處「依原版」指恢復兩處原設計：每車 action LLM 前 top_k=2 檢索，該車回答解析後即寫入、env.step 前；後車能讀前車當步寫入，同一場景庫跨 episode 共用。不是宣稱作者已在原碼中實際開啟這兩處。

M21 的唯讀、固定兩筆與凍結prompt均是底層驗收階段，不列為新正式實驗組。本次不提供 --memory-write，不把 readonly 提議擴成方法變因；歷史驗收工具保留，以免刪除證據。正式應用只用 --memory off/on，預設off。

## 基線與編號

開始時 qwen-local／ff7eae5，工作樹乾淨。原作者副本未修改；M17、安全公式／門檻／優先權／signed distance／速度處理、既有20 seeds及off基線均不改。

| 編號 | 內容 |
|---|---|
| M22-R1-01 | [original_memory.py](../../../llm_controller/original_memory.py)：可寫原版session，期初採用既有庫目前snapshot/count，只由本session已核對寫入推進，不要求每回合固定初始快照 |
| M22-R1-02 | [qwen_step.py](../../../llm_controller/qwen_step.py)：每車完整回答與動作驗證後立刻update，再輪下一車；所有車結束才env.step。先保存prepared紀錄，回傳verified前不宣稱成功 |
| M22-R1-03 | [主入口](../../../Run_multi_CAV_LLM.py)／[qwen_episode.py](../../../llm_controller/qwen_episode.py)／[memory_mode.py](../../../llm_controller/memory_mode.py)：--memory off/on與--memory-config，on只建一次session供整回合多步共用，finally關閉；配置缺漏拒絕，不回雲端 |
| M22-R1-04 | [單步驗收](../../../validation/run_qwen_single_step.py)／[Qwen管理器](../../../validation/run_qwen_live_session.py)：傳遞明確on設定；管理器保留原資源／ownership／停服限制，驗證session寫入數；off命令預設不變 |
| M22-R1-05 | [Chroma backend](../../../llm_controller/chroma_memory.py)／[memory服務](../../../validation/serve_local_memory.py)：status新增record count與resolved store path hash，client可確認連的是指定庫。沿用原manifest／embeddings／source／ID與寫後核驗 |
| M22-R1-06 | [check_original_memory.py](../../../validation/check_original_memory.py)／[accept_original_memory.py](../../../validation/accept_original_memory.py)／[手動腳本](../../../validation/accept_original_memory.sh)：原方法對照、空庫與同一步可見、跨scope共用、寫入錯誤及CLI驗收 |

## 儲存原文與四欄完全依原方法

不複製／改寫 generate_comment。直接呼叫既有 action agent 的 memory_update，先以 Capture.addMemory 接收它產生的原文字與四欄，再交給本地session寫入。只抑制該原函式過早印出的「New mem has been added」訊息，避免實際HTTP尚未成功就誤報；成功／失敗以JSON更新receipt為準。

- query仍是prompt_info.strip後最後兩行join，保留前導newline；stored text仍為最後一行。
- human_question='None'，negotiation_result='None'；不是本次negotiation輸出。
- final_action為原單元素動作陣列字串，如'[1]'，Python list在這些整數單元素案例與原NumPy字串一致（R2已確認）。
- comments呼叫原generate_comment；空資訊固定recommended to FASTER，即使實際action=IDLE也不改。它是heuristic、非步後安全／成功結果。
- 額外source只作診斷：episode／step／vehicle／code commit／方法／test_only／heuristic標記，不注入原四欄呈現文字、不作檢索篩選。
- 沒有成功episode篩選、空資訊過濾、文字去重、步後寫入或跨車凍結快照。原relation缺失仍明確失敗，不自行補造評語。

## 可見性、失敗與庫生命週期

全新空庫第一車query=0筆；該車答完即新增，後車會看到已寫入資料。k=2，所以庫有3筆也只回2筆。第二episode若沿用同一庫，其第一查詢不會自動歸零。新session期初讀當前庫，不用前次config的固定snapshot，因此設定可跨回合沿用；用resolved store path SHA256、manifest、writable=true、指定tokenizer身分檢查服務，不默默建立／遷移／清空庫。

唯一ID採episode／step／vehicle，新增前拒重複、寫後核對原文／metadata／vector，並確認count只增加1與snapshot變更。這是既有M20可追蹤ID／錯誤處理的工程差異，不宣稱作者原方法原本具備。同一步後車query的snapshot必須等於前車verified寫後snapshot，沒有post-step搬移。

某車回答／寫入失敗就停止，不自動重送動作或補IDLE。**前車已寫入資料保留**；即使後車失敗導致尚未env.step，也不回滾前車記憶，這符合原逐車步前時序，而不是把所有車寫入當交易。env.step之後若失敗也不回滾既有寫入。HTTP失敗可能已入庫，事件標記failed-outcome-unknown-do-not-retry，保留資料供檢查，不盲目重試。

cooperating writer lock沿用M20；其他程式直接改庫仍無法完全阻擋。session會偵測非自己已核對寫入造成的snapshot/count變化並停止。每次status完整讀snapshot在小庫正確性驗收可用，但有O(N)開銷；沒有大型庫吞吐或即時性保證。

## 正式 CLI

```bash
# 正式主入口預設：完全關閉記憶
python Run_multi_CAV_LLM.py --backend qwen --memory off ...

# 明確開啟原版檢索＋逐車步前寫入（既有本地服務必須可寫）
python Run_multi_CAV_LLM.py --backend qwen --memory on --memory-config /home/nclab/Yizhen/.../memory-config.json ...
```

以上只展示參數形式，不是現在要求跑正式episode；實際執行必須用既有sim interpreter及原必填輸出／上限參數。正式on要求strict與m22-original-v1配置，拒絕拿R4 readonly設定冒充on。--memory-write為未知參數。off不讀配置／開庫／發memory HTTP，且若使用者同時提供memory-config會明確拒絕，避免誤會已啟用。legacy入口仍僅接受原--backend legacy，不增加雲端記憶模式。

配置的test_only是資料來源標記／fixture禁止寫正式庫的防護，不是新的memory實驗模式。fixture只能寫test_only=true的獨立測試庫；正式真回答可明確使用test_only=false的庫。主入口支援已接線不等於Spark完整正式on已驗收；目前先跑下方零步進fixture時序驗收。

## 本地測試

既有Windows Python3.13.13、stdlib／替身、PYTHONDONTWRITEBYTECODE=1。沒有真Chroma／ML／tokenizer／sim載入，未操作Spark／SSH／Qwen／交通seed。新測試：原方法AST對照R2 payload、空庫0→1可見性、四車0→1→2→3與次scope4→5→6→7、單session跨兩步、每車寫在env.step前、原四欄／評語原值、後車回覆錯誤保留前車寫入、HTTP timeout不重試、重複ID拒絕、fixture不能寫正式庫、無relation沿用原失敗、正式CLI只有off/on及3.8AST。

測試明確使用假live transport／假env.step來驗證順序，不能當成真Qwen或真交通結果。CLI負面測試會印argparse錯誤（含不支援--memory-write），屬預期拒絕而非套件故障。最終統計、逐項console、source SHA256見 [test-results.json](./test-results.json)。Spark真寫入、兩scope與原generate_comment在原sim環境的整合尚待證據，不宣稱已production on。

最終101項：100通過、1略過（真Chroma只留Spark執行），九個命令exit0。original13、off5、entry11、live-manager13、online9、single-step14、Chroma14（其中1略過）、HTTP12、replay10。編輯器本次主要Python檔無錯誤，git diff --check無whitespace錯誤。PowerShell對native stderr空行部分顯示System.Management.Automation.RemoteException，屬輸出物件包裝；逐項OK／skip與exit code均保留，不將略過稱為通過。

## Spark 下一個手動驗收

只啟memory CPU MiniLM＋Qwen tokenizer，不啟Qwen GPU、不生成回答、不env.step。建立全新空的個人test-chroma，**不預塞兩筆fixture**。兩個獨立sim capture程序使用同一庫，每個scope四台車fixture回答後立刻寫入，驗證第一scope庫筆數0／1／2／3、命中0／1／2／2；第二scope庫筆數4／5／6／7、最終8筆。這是兩個零步進scope的時序驗收，不是假稱兩個完整駕駛episode。

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
# 確認 qwen-local 且無修改後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
ss -ltn 'sport = :18082'
# 確認沒有listener後：
bash validation/accept_original_memory.sh
```

新增檔／cache／DB／結果全在 `/home/nclab/Yizhen/runs/M22-R1-original-memory-*`；不改原R4／M18庫。不要為了測試去刪現有庫。helper只SIGINT自己memory子程序、等30秒，未停就報PID，不強殺／刪鎖。

預期 `M22-R1 original memory on: PASS; query corpus counts=0,1,2,3 / 4,5,6,7; writes=8; env.step=0`、exit0。
請回傳完整console、根目錄git-commit.txt／memory-config.json／acceptance.json，以及episode-scope-1和episode-scope-2各自capture/<id>.json。失敗時再回傳service/service-console.txt及該scope console；不要下載DB／cache或自動重跑到成功。
