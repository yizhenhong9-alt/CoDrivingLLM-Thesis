# M04：真正 memory off 入口

日期：2026-11-23。Windows 本地 Python 3.13.13；未操作 Spark、未啟動模型。

## 修改前

基線 HEAD 為 80680ae2cb9db9aa637e9442ff2126ba89772f0a。
[原入口](../../Run_multi_CAV_LLM.py) 原先頂層匯入 DrivingMemory，每步執行 `memory = DrivingMemory(env)`。原 [memory.py](../../llm_controller/memory.py) 在匯入時設定 OPENAI_API_KEY；建構時建立 OpenAIEmbeddings、Chroma 並讀取 collection。action 的檢索與寫入雖然註解掉，仍有建構副作用。

原語句使用 test double 連續執行三次，建構次數為 3。此測試只計算原語句的呼叫次數，不建立真實 Chroma 或呼叫 embedding；實際副作用來源由原始碼審查確認，沒有聲稱已重跑舊記憶庫。

## 修改內容

新增 [memory_mode.py](../../llm_controller/memory_mode.py)，入口改為匯入 create_memory，並明確設定 MEMORY_MODE="off"。off 回傳 None，不匯入原 memory 模組。原 memory.py、原版 parser、action 的提示與安全邏輯保留。

on 暫時明確拋出 NotImplementedError，保留後續本地 embedding 與相容資料庫目標；不意外回退至原雲端 embedding。未知模式也報錯。

本次與 M01–M03 不同：已修改實際 Run_multi_CAV_LLM.py 的記憶初始化位置，但沒有將新版 parser 或動作檢查接入入口。

## 修改後測試結果

執行 `python validation/check_memory_off.py`，5 項全部通過。

| 案例 | 結果 |
|---|---|
| 原語句連續三次 | DrivingMemory test double 被呼叫 3 次 |
| 新入口實際設定與語句連續三次 | memory 均為 None，禁止的記憶依賴匯入嘗試為 0 |
| 原 action send_to_chatgpt method body | 使用假的 HTTP/API client 執行成功，禁止記憶物件的存取次數為 0 |
| memory on | 明確拒絕尚未完成的功能，不回退雲端 |
| 未知模式 | 明確報錯 |

證據：[測試程式](../../validation/check_memory_off.py)、[console](../M04-memory-off-test-results.txt)。method body 由 AST 擷取原始碼執行，不是複製其實作；模型與網路全部以 test double 取代。

## 實際幫助與限制

在已測範圍，移除了 off 模式不必要的記憶初始化入口；無記憶物件可供初始化 embedding、開庫、檢索或寫入。沒有以完整模擬的全域計數器量測這些操作，不能把局部測試宣稱為完整閉環證據。未量測省下多少時間或記憶體，也未宣稱碰撞率改善。

尚待 Spark Python 3.8 與真正入口整合驗證。原入口仍使用原 OpenAI agent 與原 parser，且會執行多回合與輸出影片；不可為了驗證 M04 直接執行原入口。下一階段應準備固定步數、禁止雲端請求的 Qwen 專用入口，再驗證真實 memory off。

## Git 與遠端順序

本輪未 commit、push、pull。先審查本地差異並整理版本，再將核對過的版本同步至 Spark。遠端操作由使用者手動 Remote-SSH 執行；所有新增結果限 /home/nclab/Yizhen。純離線測試不需模型服務；正式模型啟動前仍須重新查資源，正式提示另量 token 長度。
