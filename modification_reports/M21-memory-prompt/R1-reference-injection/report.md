# M21-R1：原格式記憶檢索與 CAV prompt 注入接點

2026-11-25。已完成 stdlib 介面、fixture-only 接點、預算檢查與離線測試；真 Qwen tokenizer 驗收待使用者手動執行。沒有啟用正式 memory on 或實作 M22 寫入。

## 基線與本次變更

開始時 qwen-local／50d7f5d0ccc800d33d9a6819cc455a65abadedd6、工作樹乾淨。沿用已核對的 AGENTS／使用者操作邊界，未改原作者副本、M17 prompt、安全 helper、signed distance、速度處理或既有實驗結果。

- M21-R1-01：[memory_prompt.py](../../../llm_controller/memory_prompt.py)：原 query 擷取、原四欄驗證、原 relative_memory 文字、整筆候選刪減與完整 chat-message token 預算。
- M21-R1-02：[qwen_step.py](../../../llm_controller/qwen_step.py)：加入可選 memory_prompt 接點。預設 None，原 off prompt 與流程不變；有接點時只允許 fixture 且不步進。記憶只進 action prompt，negotiation 原文不變。尚無正式 memory CLI，factory on 仍拒絕。
- M21-R1-03：[check_memory_prompt.py](../../../validation/check_memory_prompt.py)：9 項新測試及既有 off／step／entry 回歸。
- M21-R1-04：[accept_memory_prompt.py](../../../validation/accept_memory_prompt.py)／[手動腳本](../../../validation/accept_memory_prompt.sh)：只讀既有 M16 action messages，以固定兩筆原模板作合成候選，用既有 Qwen tokenizer 與 chat template 計數；不跑生成或交通模擬。
- M21-R1-05：R7 Spark 成功回傳補記、本報告與測試摘要／source hashes。

## 保留語意及差異

query 仍為 prompt_info.strip().split('\n') 最後兩行 join，不額外 strip／正規化；儲存文字與更新不在本次範圍。k=2，沒有新增 score threshold、成功經驗篩選或車號過濾。查回 ID、text、source、distance、score 只進診斷紀錄，CAV 看到的每筆仍是原句 `- Last time {negotiation_result}, you choose to {final_action}, it is {comments}` 與原結尾說明，沒有把 None 改實際 negotiation，也沒有重寫 action 或 heuristic comments。連原作者空庫仍附結尾句的行為也保留；診斷另明確記錄 0 命中，不宣稱有有效經驗。

記憶段放在現有 Qwen attention points 之後、passing orders 之前；插入段去除後必須還原原 off prompt。這是目前 Qwen 重組 prompt 的接點，不宣稱整份 prompt 與原作者逐字相同。counter 必須計算完整 messages＋Qwen chat template；預設 2048 context、256 output。先試 2 筆，再 1 筆，再 0 筆；每次保留全部情境／規則／輸出指示，從尾端整筆移除候選。仍超出就拋錯，不默默截斷。

RetrievalPrompt 要求 `original-prompt-info-last-two-lines-v1` manifest，拒絕把 R7 fixtures schema 直接當正式庫；建立／遷移新 schema 庫尚未安排。M21-R1 的檢索介面只讀，前後 status snapshot 必須一致；它是明確的 retrieval-only 測試階段，不是原作者完整 memory-on 的固定快照替代品。status 讀全庫的開銷也尚未量測，不能當 production 效能設計。M22 若做原版參考更新，仍須每車回答後、env.step 前寫入，允許後車讀前車當步資料、跨 episode 共用庫；本次沒有改成 post-step 或凍結庫。

## 本地測試

既有 Windows Python 3.13.13、stdlib／替身、PYTHONDONTWRITEBYTECODE=1，沒有 ML 載入、下載、網路請求、Spark／SSH 或實驗執行。

| 檢查 | 結果 |
|---|---|
| check_memory_prompt.py | 9/9：R2 原 query／呈現逐字相符、空庫、整筆預算刪減、不改原 prompt、超限停止、readonly／schema／snapshot guard、fixture 接點／negotiation 不變、不寫入不步進、saved prompt replay、3.8 AST／無 ML 匯入 |
| check_memory_off.py | 5/5 |
| check_qwen_single_step.py | 14/14 |
| check_project_entry.py | 11/11 |
| 合計 | 39 通過、0 略過 |

初次比較 negotiation 測試失敗，原因是同一替身環境先跑 baseline，原速度 clamp 已把 7 改成 5，再跑比較造成初始狀態不同；已在比較前還原替身速度，未改正式 clamp。初次直接 import TestCase 也讓 unittest 重複發現既有 9 項，改為 module import。最終統計不重複計數。測試摘要與 source SHA256 見 [test-results.json](./test-results.json)。本地 token counter 是替身，只能測邏輯，真 token 數尚未有證據。

## Spark 下一個手動驗收

先核對分支／工作樹，乾淨才 pull，之後執行：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
# 確認 qwen-local 且無修改後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
bash validation/accept_memory_prompt.sh
```

腳本在個人 runs/M21-R1-memory-prompt-* 建立輸出，從既有 runs/M16-one-episode 遞迴尋找 step-0000.json 所在目錄；只有一個目錄才自動使用，否則停止，可另用 --step-dir 指定正確已存在目錄。只讀 step-*.json、不覆寫 M16。不需要啟動 Qwen 或 memory 服務，沒有服務埠與模型權重載入；僅在現有 Qwen 環境載入本地 tokenizer，local_files_only、offline、socket network block，cache／tmp 全在個人目錄，不裝套件。

預期 PASS、exit 0；完整 M16 為 404 action prompts。acceptance.json 保存加入記憶後 messages、候選／注入筆數、每輪預算、來源 step hash 與 prompt hash。候選順序刻意固定為兩筆 fixture，**不是實際 top-2 檢索排名**；只驗證格式與 token 預算，不能宣稱已做真檢索＋Qwen 端到端測試。請回傳完整 console，尤其 action_count、max_input_tokens、exit code 與結果目錄；失敗原樣保留，不自行放寬 context。

下一關仍需新 schema 隔離庫的真檢索接線、正式設定／生命週期與 Qwen 最小驗收。只有這些通過，才能開放 live retrieval-only；M22 更新另行接線，不能以本次測試宣稱完整 production on。

## 原專案 HTTP 說明

原 [memory.py](../../../llm_controller/memory.py) 直接在模擬 Python 程序內 import LangChain Chroma／OpenAIEmbeddings，建立本地 persistent Chroma。沒有此專案自建的 localhost memory HTTP server，也沒有以 HTTP 隔開模擬與 memory 的 Python 環境。原 OpenAI LLM／embedding 使用雲端 API，action client 還設定本機 7890 proxy；這些網路請求不是 R7 的本機跨環境隔離。R7 是為保留既有 3.8 sim、讓 MiniLM／Chroma 留在 3.12 而新增的架構差異。
