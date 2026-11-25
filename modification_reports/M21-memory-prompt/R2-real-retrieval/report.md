# M21-R2：真檢索候選與完整 prompt 隔離驗收

2026-11-25。程式與本地替身驗證完成，Spark 真模型／tokenizer 跨環境驗收待使用者手動執行。正式 memory off、factory on 拒絕與 M21-R1 fixture-only 限制保持不變；無 Qwen 生成、交通步進或 M22 更新實作。

## 基線與編號

開始時 qwen-local／d8a759f，工作樹乾淨。承接已審查的 M21-R1 回傳原檔：404 份均保留兩筆合成記憶、最大 1129＋256=1385 tokens。那是固定候選順序，本次才改用隔離庫的真檢索結果。沒有重跑 M16 或 20 seeds，不修改原作者副本／prompt／安全公式／門檻／優先權／signed distance／速度處理，不安裝新套件。

| 編號 | 新增內容 |
|---|---|
| M21-R2-01 | [accept_retrieval_prompt.py](../../../validation/accept_retrieval_prompt.py)：3.8 parent 建立獨立測試庫、寫兩筆原模板、重開唯讀、真檢索、跨環境 token 計數、以 RetrievalPrompt 組 prompt |
| M21-R2-02 | [count_memory_candidates.py](../../../validation/count_memory_candidates.py)：既有 Qwen 環境只載 tokenizer，計算實際候選 2／1／0 筆完整 messages，回傳 messages hash→token count |
| M21-R2-03 | [memory_service_session.py](../../../validation/memory_service_session.py)：測試用 owned child 生命週期／個人 cache／offline 設定；只 SIGINT 自己子程序，30 秒未停回報 PID，不強殺 |
| M21-R2-04 | [accept_retrieval_prompt.sh](../../../validation/accept_retrieval_prompt.sh)：使用者手動 Spark 入口，保存 commit、資源與 console，每次建立全新個人 run |
| M21-R2-05 | [check_retrieval_prompt.py](../../../validation/check_retrieval_prompt.py)：真 loopback HTTP＋Chroma／encoder／tokenizer 替身，六項管線與限制測試 |

## 驗收流程

1. 使用 `original-prompt-info-last-two-lines-v1` manifest 在本次 run 新建 Chroma，**不重用或遷移 R7 的 fixtures schema DB**。寫入 R2 兩筆原文／原四欄，加隔離 test_only source。沿用 R5 套件 baseline／R6 本地權重 hash guard，不下載或重新轉換。
2. 額外送出 `word ` 重複 300 次的寫入，預期 HTTP 失敗，核對邏輯 snapshot 不變；測試目的為驗證實際 MiniLM 超長拒絕，不進正式庫。
3. 停止自己的 create 服務，再以另一程序唯讀開同一隔離庫。從既有 M16 step 0／35 車 3 保存 prompt 還原 scenario，核對 query 與原 R2 逐字相同。
4. 由 Python 3.8 stdlib client 真 HTTP 查詢 top-2，核對對應 top-1、原文／四欄／來源。保存實際候選、順序、distance／score 與 M16 source hash，不假造排序。
5. 既有 Qwen 3.12 環境只載本地 tokenizer，對實際候選各完整前綴計數；local_files_only、offline、socket block，沒有生成／載入權重或服務呼叫。回覆包含 cases 檔 hash 及完整 messages hash→count；tokenizer 子程序有 120 秒 timeout。
6. Python 3.8 的 RetrievalPrompt 再查同一唯讀庫，counter 只接受已計數的精確 messages hash；未知 messages 或前後候選／snapshot 不同即失敗。組 prompt、保存實際注入 ID／排除理由／token 預算；最後核對 corpus 未改，3.8 未匯入 ML。

這不是新 tokenizer HTTP 服務；只有既有 memory HTTP。這個離線批次計數流程也不是未來 live 每車 token 計數生命週期的最終設計。status snapshot 讀全庫，只用兩筆隔離驗收，尚未有大型庫效能證據。兩筆真檢索接線仍不能證明全面交通語意／安全或 production on 完成。

## 長度／大小超限如何處理

| 層級 | 現有限制 | 超限行為 |
|---|---|---|
| 文字輸入 | 每筆最多 16384 字元，必須非空 | client／底層驗證拒絕，不截斷 |
| MiniLM embedding | 含 special tokens 最多 256 tokens | inference 前拒絕，HTTP 回傳失敗，不寫入該筆、不退回雲端 |
| memory HTTP | JSON request／response 上限各 1 MiB，為 UTF-8 bytes，包含 metadata 等包裝 | request 在 client 或 server 拒絕；response 超限拒收／服務報錯，不默默裁切 |
| Qwen 完整 prompt | input＋預留 output ≤ context（目前 2048、預留 256） | 按已回傳順序從最後一筆整筆排除，2→1→0；診斷保存嘗試計數／排除原因，不改情境、安全規則與輸出格式 |
| 零筆記憶仍超 Qwen context | 原完整 prompt＋原空記憶結尾也放不下 | 明確失敗，不送出該次 Qwen 請求；不是默認 IDLE 或自動 memory off |

字元數、UTF-8 bytes、MiniLM tokens、Qwen tokens 是不同量，不可互相替代。合成記憶與真實命中採相同 Qwen budget 規則。原 metadata 四欄不為縮短而改寫，沒有摘要／切字／改安全門檻。對一般寫入錯誤或斷線不能一概保證沒有入庫，R7 已明確標記寫入結果可能未知、禁止盲目重試；只有像本次可核對 snapshot 的隔離超長測試，才能證明該測試沒改庫。

## 本地測試

Windows 既有 Python 3.13.13、stdlib／替身、PYTHONDONTWRITEBYTECODE=1。沒有真 Chroma／ML／tokenizer 匯入、無模型下載、Spark／SSH／Qwen 生成或交通實驗。

新增六項均通過：HTTP→LocalMemory→Chroma 替身→候選→token map→RetrievalPrompt 往返；候選改變／未知 messages hash 停止；2→1→0 仍保留原 base prompt，零筆仍超限停止；16384 字元／1 MiB client 限制拒絕且 snapshot 不變；encoder 例外經 HTTP 傳遞且未寫入；Python 3.8 AST／無 ML 匯入。真正 256-token 邊界未在 Windows 測試，交由本次 Spark 長文字測試；Bash／真程序生命週期亦未本地實跑。

最終測試命令、exit code 與 source hashes 見 [test-results.json](./test-results.json)；console 保存於同目錄。未修改既有 production 模組。

最終合計 27 通過、0 略過：check_retrieval_prompt.py 6、check_memory_prompt.py 9、check_memory_http.py 12，三個命令 exit 0。四個新增 Python 檔編輯器無錯誤。PowerShell native stderr 的空行在 console 中部分顯示 System.Management.Automation.RemoteException，為輸出包裝現象，非 Python traceback；逐項 unittest 與 exit code 如實保留。

## Spark 使用者手動執行

核對 qwen-local 與無未提交修改後才 pull；若 18082 已有 listener，停止本次操作，不處理他人程序。

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
# 確認 qwen-local 且工作樹乾淨後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
df -h /home/nclab/Yizhen
ss -ltn 'sport = :18082'
# 確認沒有 listener 後：
bash validation/accept_retrieval_prompt.sh
```

所有新檔／cache／DB／結果在 `/home/nclab/Yizhen/runs/M21-R2-retrieval-prompt-*`。既有模擬、memory、Qwen 套件環境不變，只在 memory 環境 CPU 載 MiniLM，Qwen 環境載 tokenizer。腳本自動找唯一的既有 M16 step 目錄；歧義時停止，可加 --step-dir 指定已有目錄。

預期 console 為 `M21-R2 real retrieval -> prompt: PASS; cases=2; ...`、exit 0。請回傳完整 console、acceptance.json、git-commit.txt、tokenizer/counts.json；若失敗則加 create/service-console.txt／readonly/service-console.txt／tokenizer/console.txt。不要下載 cache 或 test-chroma。失敗結果保留，不升套件、放寬限制或刪鎖。

通過後才安排正式配置／生命週期及最小 live retrieval-only 驗收；M22 原版逐車步前寫入仍是獨立待辦。
