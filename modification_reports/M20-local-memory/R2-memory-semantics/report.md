# M20-R2：原版 memory 語意、M16 離線重播與實作差異

日期：2026-11-25。狀態：靜態流程審查與保存 prompt 重播完成。只有新增分析工具／結果／報告與索引，未修改 memory 生產程式、prompt 或安全 helper，未操作 Spark、模型或資料庫。

## 為何在接 memory on 前做

使用者要求先確認 memory 寫入時機、內容、查詢 key、回傳及與原版的差異。不能把底層儲存成功等同於記憶方法等價，也不能等串完後才辨認是否意外改變原方法。

分析來源：原作者本地 [action agent](../../../../CoDrivingLLM/llm_controller/llm_agent_action.py)、[memory](../../../../CoDrivingLLM/llm_controller/memory.py)、[formatter 與評語](../../../../CoDrivingLLM/llm_controller/prompt_llm.py)、[主入口](../../../../CoDrivingLLM/Run_multi_CAV_LLM.py)，並對照本研究目前 [Chroma adapter](../../../llm_controller/chroma_memory.py)、[本地 embedding／SQLite 參考](../../../llm_controller/local_memory.py)、[Qwen step](../../../llm_controller/qwen_step.py)。Git HEAD 為 c486a549ea965ee1149df432c0adb481a9d4c9b5；先前 R1 報告已有未提交回傳補記，保留不覆蓋。

## 原版其實有兩個獨立開關

當前原始碼 retrieval 與 update 兩個呼叫都註解。不存在能單靠開啟單一 memory flag 就啟用所有流程的實作。若手動恢復兩處：

1. 每一步先建立 DrivingMemory，開啟同一 env.spec.id 對應的持久化目錄。
2. negotiation LLM 根據當前衝突產生通行建議；不使用 memory。
3. 逐台 CAV 依序組 prompt_info。
4. 各車送出 action LLM 前，relative_memory 將 prompt_info 最後兩行當 query，top_k=2。
5. 查詢文字經 embedding 後送 Chroma，取回相近 document 的 metadata，組成 past_memory 插入 action prompt。
6. action LLM 回答並解析成單元素動作陣列。
7. 隨即 memory_update，取該車 prompt_info 最後一行與動作、規則評語，呼叫 addMemory。**此時尚未 env.step，也尚不知道實際後果。**
8. 所有車都完成後，主入口才 env.step。

若寫入成功，同一步較後處理的 CAV 可能讀到前一台剛寫入的資料；不是所有車共用步開始時的固定快照。路徑只有場景名，沒有 episode／seed 隔離，理論上可跨回合／重新執行共用既有庫；是否已有資料須另查，不能由目錄存在推定。只有寫入或只有檢索也可分別恢復，這三種模式不能混稱同一個 memory on。

## 儲存的內容

有 most_dangerous_info 時，formatter 以固定英文模板輸出：

```text
 Currently, the most dangerous collision information with the ego vehicle is as follows:Ego is _<relation>_ to conflict point than other vehicles considering current speed and distance, Ego vehicle speed minus other vehicle is <delta speed>
```

relation 由原 TTCP 差門檻分類；delta speed 是原 helper 的速度差。該尾段不包含完整場景、車號配對、原始 TTCP、所有車位置，也沒有完整 negotiation 建議。原 helper 只選後通行對象中的危險項目，空資訊不代表完全沒有衝突，見 M17。

沒有選出危險項目時，最後一行為含前導空白的 ` Conflict info is empty`。原更新方法把它當成可儲存情境，不是跳過。

addMemory 建立 LangChain Document：

| 欄位 | 原更新方法填入的內容 | 作為 embedding 輸入？ |
|---|---|---|
| page_content | prompt_info.strip().split('\\n')[-1] 的情境尾行 | 是 |
| human_question | 字串 "None" | 否 |
| negotiation_result | 字串 "None"，不是當步 negotiation 結果 | 否 |
| final_action | 原單元素 NumPy 陣列的字串，例如 "[3]" | 否 |
| comments | generate_comment(relation, action_id)，空資訊則固定 recommended to FASTER | 否 |

comments 沒有使用步後 reward、crashed、到達或 episode 成敗。空資訊時的 recommended to FASTER 甚至不是依據該筆實際選擇動作生成。原評語與動作語意是否合適需另審，不在本次修改。metadata 不含來源 seed／step／vehicle／版本；不能據此追蹤該經驗是否來自測試回合。

原 addMemory 沒有由作者指定穩定 memory ID／防重規則，也沒有內容去重；反覆相同 page_content 可成為多筆不同 metadata 記憶。寫入例外被 catch 並列印，外層仍會列印 New mem has been added；單看該訊息不能證明入庫成功。

## 查詢 key 與回傳

這不是用 vehicle_id、step 或動作做 key-value lookup。query_scenario 是 `"\\n".join(prompt_info.strip().split("\\n")[-2:])`，以文字向量做相似搜尋；內部 document ID 只是識別資料用，原 helper 沒用它作查詢條件。

Chroma helper 呼叫 similarity_search_with_score(query, k=top_k)，預設 k=5，但 action caller 明確傳 top_k=2；沒有額外 score threshold、成功資料篩選或車號／seed 過濾。此 Python 層丟棄 document 原文與距離，只回傳 metadata 清單。

relative_memory 再產生：

```text
- Last time None, you choose to [3], it is recommended to FASTER
Above messages are some examples of how you make a decision in the past. Those scenarios are similar to the current scenario. You should refer to those examples to make a decision for the current scenario.
```

上例來自 M16 step 35 車 3 的假設寫入 metadata，**僅演示如果它是命中資料時的文字格式，不是實際命中結果**。CAV LLM 不會透過這段看到該記憶的 page_content／分數／來源；它只看到 negotiation_result、動作與評語，且 negotiation_result 在原更新方法填的是 None。即使空庫沒有回傳項目，原 helper 仍附加 Above messages... 句子。

## M16 保存資料可以實際驗證的部分

[audit.py](./audit.py) 從原作者原始碼以 AST 擷取 relative_memory、memory_update 與 generate_comment 真實函式，使用 CaptureMemory 替代資料庫。從 M16 的 Current scenario 與 Rules 固定邊界還原 prompt_info，使用當時保存且通過 strict 的動作。單元素整數 Python list 的字串與原單元素 NumPy 動作陣列同為 [1]／[3]／[4]；不需要安裝 NumPy／gym／LangChain。未修改輸入檔。

結果見 [audit.json](./audit.json)，含原函式來源與 101 個 step 檔 SHA256、逐筆 query、假設 page_content／metadata 及格式示意。

| 檢查 | 結果 |
|---|---:|
| M16 step JSON | 101 |
| action scenario 成功還原 | 404/404 |
| 原 update 執行至替身 addMemory | 404/404 |
| 有 relation 的危險尾段 | 37/404 |
| 只有 Conflict info is empty | 367/404 |
| query 與 page_content 完全相同 | 0/404 |
| query 僅比 page_content 多一個前導換行 | 404/404 |
| strip 後相同 | 404/404 |

因此修正先前過度籠統的疑慮：**這批 M16 輸入的兩行／一行差異僅是前導換行；沒有內容不一致或空資訊分支失敗的重現證據。** 不應據此宣稱原版必定崩潰、文字語意不同或直接重寫 query。底線缺漏等風險仍可由異常輸入觸發，但不是本次 404 筆的實際錯誤。

更具體的限制是：367 筆會把不同車／時間的情境壓成同一句空資訊文字；單靠 embedding 無法從相同文字還原那些被捨棄的條件。M17 已指出空資訊可與通行建議並存，不能因這個標記就將記憶解讀成沒有任何衝突。

這些是 **memory off 軌跡上的離線重播**。沒有實際寫入向量庫、沒有真向量、沒有命中排名，也沒有證明 memory on 會選同樣動作。若 on 改變第一步動作，後續交通狀態也可能不同；不能把整個 off 軌跡稱成 on 的反事實實驗。M16 只是 seed 0，不代替全 M18 的文字覆蓋率。

## 現有 M20 與原版的差異：不只有雲端 embedding

| 面向 | 原版 | 目前 M20 實作／未完成項目 |
|---|---|---|
| embedding | OpenAIEmbeddings，指定套件版本預設 ada-002 | MiniLM 固定 revision、384 維、mean pooling、L2；真模型未測 |
| 長度 | 原 LangChain 的 token／長文處理 | 超過 256 tokens 拒絕，不做相同長文處理 |
| Chroma 呼叫 | LangChain Chroma 包裝，自動呼叫 embedding | Chroma 0.4.15 公開 API，傳入已算好的向量，embedding_function=None |
| 距離 | 原作者沒有明確指定 collection metric；既有庫仍需核對 | 明確 cosine，score=1-distance；不能宣稱原樣等價 |
| 路徑／collection | 相對 ./db/<env>，未按新 embedding 隔離 | 全新絕對個人路徑，獨立 collection＋manifest，不混舊庫 |
| metadata 形狀 | 四個扁平欄位，無強制來源 | 一個 JSON 字串封裝 metadata，要求 source；不自動建立原四欄 |
| ID／寫入 | helper 未指定穩定 ID，吞入庫例外 | caller 必須提供 ID，拒絕重複、入庫後核對、明確拋錯 |
| query 擷取 | 最後兩行 | LocalMemory 只接受 caller 提供的 query；尚未接原擷取器 |
| 回傳 | metadata only，分數／原文丟棄 | ID、原文、metadata、distance／score 都回傳；目前尚未轉成 CAV 記憶段 |
| 排序與資料量 | Chroma 搜尋；未做額外同分規則 | 對已回傳候選加 score／ID 排序，小庫 k 限 count；不保證 HNSW 全庫同分邊界一致 |
| 建構生命週期 | 每一步建構 | 底層提供 context manager；正式回合生命週期未接 |
| 寫入時機 | 恢復註解後是逐車答完即寫、env.step 前 | 沒有自動更新；M19 提出的步後寫入／固定快照只是後續提案，不是已完成或與原版相同 |
| 評語／成功標記 | 原 generate_comment 規則 | 底層未產生評語，不會自動補安全／成功標記 |
| 空資訊資料 | 原更新方法可存 | M20 尚無統一跳過／存入政策；不得默默過濾 |
| 正式啟用 | 原 retrieval／update 均註解 | Qwen create_memory(on) 仍拒絕；尚無正式 memory on |

原作者庫和 M20 新庫不能互相直接載入；從原碼啟用 on 也不等於目前 M20 已完整重現。安全公式、門檻、優先權與速度處理此次都未改。

## 接續順序與方法邊界

1. 本次先固定原版真實資料流程及上述差異，不必等 MiniLM 安裝完才分析。
2. 完成 Chroma＋MiniLM 真實 add／持久化重開／retrieve，保存實際文字與 metadata 往返，與原欄位逐筆對照。這是目前尚未完成的 M20 底層驗收。
3. 用小組原模板案例做檢索相關性與重複空資訊測試，不使用 M18 評估資料暗中回寫正式庫。M16 的重播資料僅作離線診斷；若用於建庫，須明確列為測試 fixture，不能當成獨立評估記憶。
4. M21 接線前，先選定並記錄是原版參考行為（逐車步前寫、原四欄與原記憶段），還是改良行為（步後寫、固定快照、實際 negotiation／語意動作名／加入來源等）。不把兩者混在一起稱為只有 embedding 替換。
5. 舊空資訊 wording 與安全評語仍保留；若改擷取／正規化，至少保存 original query 與 effective query，逐筆檢查除空白外無文字變更。不套用 M17 prompt 提案，不重算或修改安全門檻。

本項重現命令：在研究 repo 根目錄，以既有 Python 執行 `modification_reports/M20-local-memory/R2-memory-semantics/audit.py`。Python 3.13.13 stdlib，PYTHONDONTWRITEBYTECODE=1，exit 0；404 筆到達替身寫入呼叫，不代表 DB 寫入成功。沒有必要為此重跑模型、模擬或已完成的 20 seeds。
