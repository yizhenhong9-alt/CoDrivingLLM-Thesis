# M19：Qwen＋本地 embedding memory on 前置審查與實作範圍

日期：2026-11-24。狀態：原流程審查與範圍提案完成，尚未實作 memory on。本項只有新增本報告，沒有修改控制程式或既有報告索引。

## 版本與保留項目

- 分支 qwen-local；HEAD=a669568cfbe07fef08dbd44d2b353c78bdba027d。
- 開始時既有未提交：modification_reports/README.md 已修改；M17-prompt-consistency-audit/、M18-intersection-memory-off-20seeds/ 未追蹤。全部保留，未 commit、stash、reset 或切換分支。
- 查無 C:/AGENTS.md、工作區 AGENTS.md、repo AGENTS.md，repo 遞迴亦無 AGENTS.md。Git 以單次 safe.directory 讀取，未修改全域設定。
- 已讀 M17、M18、正式入口交接、原部署交接文末 30B 更正與 Qwen 替換計畫；較舊進度由 M16／M18 覆蓋。指定 Qwen 維持官方 30B-A3B Instruct-2507 FP8。
- M18 的 seeds 0–19 保留為 memory off 歷史基線；不重跑、不回填、不用於不加區分的線上訓練記憶。M17 文字提案不套用。

## 原 memory 全流程

1. 建立：[memory.py](../../llm_controller/memory.py) 匯入 LangChain／Chroma／OpenAIEmbeddings，匯入時改 OPENAI_API_KEY；建構時使用雲端 embedding、相對工作目錄的 ./db/<env.spec.id>，並透過私有 collection 讀出全部 embeddings 計數。舊主入口原本每一步建構，目前由 [memory_mode.py](../../llm_controller/memory_mode.py) 的 off 返回 None；on 主動拒絕。
2. 檢索：[relative_memory](../../llm_controller/llm_agent_action.py) 將 prompt_info.strip() 後最後兩行作 query，以 top_k=2 檢索，僅取 metadata，丟棄距離分數、document 與 ID。Chroma helper 預設 k=5，但此呼叫明確用 2。
3. 注入：同檔 send_to_chatgpt 的檢索呼叫已註解，past_memory 固定空字串；legacy prompt 仍有空的歷史經驗段。原設計把 negotiation_result、final_action、comments 組成文字範例；沒有注入 negotiation LLM 的流程。
4. 更新：llm_controller_run 的 memory_update 呼叫已註解；原位置在各車回覆之後、env.step 之前。memory_update 只存最後一行，不同於檢索的最後兩行；human_question 與 negotiation 都是字串 None，action 是動作陣列字串。用底線 regex 擷取 relation，再呼叫既有 generate_comment。沒有步後碰撞／到達回饋，也不是獎勵學習。
5. 風險：strip 會去掉最外側空白，但空資訊比較字串含前導空白；實際 formatter 的尾端亦有空白行，不能假定空資訊一定被正確辨識。relation[0] 未防空；缺底線可能拋錯。addMemory 吞例外只列印，外層仍可能列印新增成功。comments 是規則評語，不能標成實測安全。
6. 向量庫：repo 有 llm_controller/chroma/chroma.sqlite3，但原建構路徑是 ./db/<env>，不能因檔案存在就認定會載入。此次未開啟／遷移此資料庫，也未確認其模型、維度、內容或授權來源。不同 embedding 空間不能混用。

## 正式 Qwen 接點

[qwen_step.py](../../llm_controller/qwen_step.py) 每步明確 create_memory(env, "off")，回報 memory_mode=off，action prompt 不含 memory 段。[qwen_episode.py](../../llm_controller/qwen_episode.py) 的 summary 亦固定 off，且主入口尚無 memory CLI。單改 factory 無法啟用完整流程。

[vehicle_actions.py](../../llm_controller/vehicle_actions.py) 負責 episode／step／車輛物件身分、回覆完整性及可用動作檢查，不負責記憶。記憶內歷史車號不可當成當前動作；保留此檔與原 parser 邊界。

## 後續具體實作範圍（預定編號，尚未完成）

### M20：本地 embedding client 與隔離記憶庫

- 新增獨立 Qwen 專用模組，不匯入舊 memory.py，不改 legacy helper。模擬 Python 3.8 只用 stdlib HTTP 呼叫 Spark loopback embedding service；模型載入留在獨立 Spark Python 環境，由使用者手動操作。拒絕非 loopback、重新導向、proxy／雲端 fallback。
- 初步候選 sentence-transformers/all-MiniLM-L6-v2，英文情境、CPU 執行以降低與 Qwen GPU 競爭；模型仍須查證官方來源、固定 revision、pooling、維度、套件與 ARM64 可行性後才定版，不能現在宣稱部署可用。
- 小規模先用 stdlib SQLite 儲存文字、metadata 與向量，明確 cosine 計分、固定同分排序、top_k=2；避開模擬環境 LangChain／Chroma 升級。這是新的檢索實作，不宣稱與舊 Chroma 分數等價。
- manifest 固定模型／revision／維度／正規化／pooling／query schema／場景／版本，任一不符即拒絕；新建獨立庫，舊庫不直接匯入。檢查有限非零向量、維度、回覆數與輸入順序。
- 遠端模型、DB、快取、暫存、環境及結果的 resolved path 限 /home/nclab/Yizhen，含 symlink 逃逸檢查。off 不建目錄、不碰 DB、不發 embedding 請求。

### M21：Qwen 記憶檢索與 prompt 注入

- CLI 增加明確 memory off/on 與 memory config，預設 off；每回合建構一次，跨步共用，關閉時釋放。不改 negotiation prompt。
- query 與存入文字共用同一版本化擷取器，保留既有 formatter 輸出；對空資訊／無 relation 明確處理，不從最後兩行猜測、不套用 M17。保存原 query 和缺資訊原因，不補造風險數值。
- 先完成唯讀檢索路徑與離線建庫工具；memory on 若空庫必須回報 0 命中，不能說有效經驗已啟用。每筆保存 ID、分數、來源、庫快照雜湊與 embedding manifest。
- action prompt 僅加入固定邊界的歷史資料段，保留其餘 off 文字、輸出格式、可用動作與全部安全 helper。歷史車號不映射成當前車號，歷史動作不繞過 parser／ActionBatch。
- 使用指定 Qwen tokenizer 與 chat template 檢查完整輸入＋輸出預算；超出時依固定順序減少完整記憶筆數，仍超出則停止。保存候選／實際注入／排除原因，不默默截斷 prompt。

### M22：寫入與資料來源

- 分開唯讀 evaluate 與明確 collect 模式；正式比較使用固定唯讀快照，測試 seeds 不回寫該快照。建庫資料來源、seeds、prompt／parser／程式版本另記，避免測試資料洩漏。
- 保留原 relation 與 generate_comment 內容，不改安全公式／評分規則；評語標為 heuristic，另存實際步後 outcome，不把評語當作成功標籤。
- 所有車回覆通過檢查、env.step 成功且步紀錄保存後才允許寫入；以 run／episode／step／vehicle 唯一鍵防重。失敗、未步進、fixture 不寫正式庫。查詢同一步固定前一個快照，避免後處理的車看到前一台剛寫入的資料。
- DB 寫入錯誤需明確失敗並保留已步進事實，不重送動作或聲稱新增成功。若要改成僅成功回合入庫，需另列資料選取方法，不暗中改既有評語政策。

### M23：Spark 手動分階段驗收

- 先離線替身驗證，再由使用者執行 CPU embedding 自測／建庫／token 計數，最後獨立的新單步或短程 memory on；不重部署 Qwen，不重跑已完成 20 seeds。
- 每階段保存 console、JSON、完整 messages、查詢／命中／注入／寫入紀錄、manifest、資料快照及 source hash。任何交通改善結論須有新證據，本報告不宣稱 memory on 已可運行。

## 本項測試與限制

2026-11-24，本地既有 Python 3.13.13（C:/Users/user/miniconda3/python.exe），設定 PYTHONDONTWRITEBYTECODE=1；使用 stdlib 與既有替身，未安裝套件、未載入任何模型、未呼叫 API、未啟動模擬。

| 檢查 | 結果 |
|---|---|
| validation/check_memory_off.py | 5/5 通過；目前 on 仍明確拒絕，off 不接觸舊記憶依賴 |
| validation/check_vehicle_actions.py | 13/13 通過；車輛順序、缺漏、重複、過期回覆與動作檢查保留 |
| Git 版本／未提交盤點 | 已核對；既有修改完整保留 |

本項為文件變更與現況測試，不是 memory on 實作測試。Spark 當下資源、embedding 模型／服務、實際 DB round-trip、token 預算與真 Qwen memory on 效果均尚未驗證。安全公式、門檻、優先權、signed distance、5 m/s 處理、M17 prompt 文字與原始 20 seeds 資料全部未改。
