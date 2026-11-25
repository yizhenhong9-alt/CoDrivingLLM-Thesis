# M20-R7：跨環境 loopback memory 服務

## Spark 成功回傳補記（M20-R7-06，2026-11-25）

使用者於聊天回傳驗收 console：status=PASS、client Python 3.8.20，create／reopen 均 PASS，exit 0。
結果目錄 `/home/nclab/Yizhen/runs/M20-R7-memory-http-sLqgva`；兩階段 snapshot SHA256 均為
`7d9c74bc37bf48becd61104890ad8c8c3d6f45ab0b8fdf8b238a934a69466ed0`。
依已提交腳本的檢查可確認 Python 3.8→3.12 HTTP、兩筆測試資料往返、跨服務程序重開及唯讀拒寫通過。
目前證據是使用者貼回 console，未取得該 run 的 git-commit.txt、acceptance.json 原檔或兩份 service-console；不自行填入未核對的遠端 commit 或宣稱已審閱這些檔案。
此結果取代下文建立時「Spark 待驗收」狀態；仍不代表全面交通語意、安全改善或 production memory on 完成。

日期：2026-11-25。程式與 Windows stdlib 替身驗證完成；Spark Python 3.8→3.12 真整合待使用者手動執行。正式 memory off、factory on 拒絕狀態與駕駛流程均未修改。

## 基線與編號

開始時 qwen-local／e26727047ca76719f14f7bf43d218441762ed337，工作樹乾淨；父層與 repo 遞迴未找到 AGENTS.md。未修改原作者副本。已讀 M19、M20 R1–R6、原交接與 step6 console；R6 成功證據補入 [R6 報告](../R6-minilm-embedding-acceptance/report.md)，hash 逐字以 console 為準。

| 編號 | 內容 |
|---|---|
| M20-R7-01 | [memory_http.py](../../../llm_controller/memory_http.py)：Python 3.8 stdlib client，status／retrieve／add，預設 k=2；無 proxy／redirect／fallback／自動重試 |
| M20-R7-02 | [serve_local_memory.py](../../../validation/serve_local_memory.py)：單一 127.0.0.1 HTTPServer，直接 LocalMemory→CPU encode→Chroma；不疊 embedding HTTP |
| M20-R7-03 | [accept_memory_http.py](../../../validation/accept_memory_http.py) 與 [手動腳本](../../../validation/accept_memory_http.sh)：模擬 3.8 作 client，啟動／停止自己的 3.12 子程序，隔離 DB，兩筆原模板，跨程序重開核對 |
| M20-R7-04 | [check_memory_http.py](../../../validation/check_memory_http.py)：本地 HTTP 與 Chroma 替身、錯誤、回覆核對及 Python 3.8 AST 相容檢查 |
| M20-R7-05 | R6 證據補記、本報告、索引與逐項 console／source hashes |

## 服務行為與限制

三個 POST endpoint 都要求 protocol=m20-r7-v1 與完整相同 manifest。新建 DB 要明確 --create；既有庫預設 adapter 唯讀，--writable 才可新增。只接受 1 MiB 以內請求／回應、有 Content-Length、無 Transfer-Encoding；socket timeout 30 秒。只綁 127.0.0.1:18082；無遠端 host 選項，不啟動雲端連線。

client 核對 query hash、寫入 ID／文字 hash／metadata hash、命中 ID 不重複、source 非空、有限 cosine distance／score。服務沿用 Chroma adapter 的明確 embeddings、embedding_function=None、manifest guard、重複 ID 拒絕及寫後 get 核對。metadata 原值封裝保存，不用 source 改寫原四欄。寫入成功才回傳 receipt；後端錯誤回傳失敗，不變成空命中。HTTP 錯誤關閉 response，傳輸錯誤向外傳遞，沒有重試；斷線或寫後核對失敗可能已入庫，應先檢查，不能盲目重送。回應錯誤僅列型別與結果未知標記，不記錄 query／ID／metadata／後端例外全文。

Spark 啟動先核對 R5 runtime.json 的完整套件版本集合，再離線讀 R6 source-api.json／download.json／conversion.json，重驗既有檔案 hash 與衍生 safetensors hash；不下載、不再轉換。服務只在既有第三環境載入 MiniLM，所有 cache／tmp 設定限個人 run 目錄，CPU 單執行緒、offline、local_files_only。原 embedding-only 服務保持原狀。

單序列服務適合目前逐車同步流程，無並行吞吐保證。loopback 沒有身分認證，同帳號／同主機其他程序仍可能呼叫；不宣稱帳號隔離。CPU 推論沒有獨立強制終止 deadline。Chroma 唯讀只在 adapter 層，開庫仍可能更新內部檔案。status 邏輯 snapshot 會讀全庫，只作小型驗收，不放進每車請求。新增協定沒有生產資料 schema／實驗更新政策。

## 本地驗證

使用既有 Python 3.13.13，PYTHONDONTWRITEBYTECODE=1；無新套件、無真 ML 匯入、無模型下載／載入、無 Spark／SSH／Qwen／交通 seed 執行。

新增 12 項測試涵蓋：空庫、原文字空白與四欄／source 往返、重複 ID／唯讀拒寫、manifest 不符、輸入與 request size、後端錯誤及不洩漏全文、錯誤 receipt／query hash／距離／重複結果、無 proxy／redirect、HTTP framing、timeout 傳遞、HTTP→LocalMemory→Chroma 替身明確 embeddings、R6 receipt 不符拒絕及 3.8 語法／無 ML 匯入。

第一輪 9 項雖通過，但發現未關閉 HTTPError response 的 ResourceWarning；已修正 close，最終 12 項無該警告。最終逐項結果與回歸統計見 [test-results.json](./test-results.json) 及本目錄 console。本地 3.8 僅 AST 檢查，不能代替真 3.8 執行；Bash 未在 Windows 實跑，Spark 驗收尚未通過。

| 檢查 | 最終結果 |
|---|---|
| check_memory_http.py | 12/12 通過 |
| check_local_memory.py | 15 通過、1 略過（Windows symlink 權限） |
| check_chroma_memory.py | 13 通過、1 略過（真 Chroma 限 Spark） |
| check_memory_off.py | 5/5 通過 |
| check_vehicle_actions.py | 13/13 通過 |
| 合計 | 58 通過、2 略過；五個命令 exit 0 |
| 編輯器 diagnostics／git diff --check | 四個新增 Python 檔無錯誤；無 whitespace 錯誤 |

PowerShell 將 native stderr 包裝成物件，保存輸出中少數空白行顯示 System.Management.Automation.RemoteException，symlink 中文系統訊息亦有字碼損失；這些不是 Python traceback，逐項 unittest OK／skip 與原始 exit code 均已保存，不冒稱略過項目通過。

## Spark 使用者手動驗收

本次 commit／push 後，在 Spark 終端機執行下列命令。若工作樹非乾淨、分支不符或 pull 非 fast-forward，先停止保留現況，不 reset／stash。腳本不安裝套件、不改 Qwen／sim 環境，不下載模型，不執行交通模擬。

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis branch --show-current
# 確認 qwen-local 且無修改後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis log -1 --oneline
free -h
df -h /home/nclab/Yizhen
ss -ltn 'sport = :18082'
# 若已有 listener，先停止本次驗收，不處理他人程序。
bash validation/accept_memory_http.sh
```

腳本建立 `/home/nclab/Yizhen/runs/M20-R7-memory-http-*`。3.8 parent 先啟動 3.12 create 服務，確認空庫、寫入兩筆 test_only fixtures、拒絕重複 ID、top-2／top-1、原文／四欄／source 完全相同；停止自己的子程序後，啟動全新 3.12 程序唯讀開庫，核對真向量命中、拒寫及 snapshot 相同。兩階段 client 都確認沒有匯入 torch／transformers／chromadb。子程序只用 SIGINT 停止，等待 30 秒；若未退出回報其 PID，不自動 kill 或清除鎖。

預期最後為 PASS、exit 0，acceptance.json 有 create／reopen 兩階段 PASS。請回傳完整終端 console、acceptance.json、create/service-console.txt、reopen/service-console.txt。失敗結果保留，勿刪環境／DB 或自行升套件；全新重跑會使用另一隔離目錄。服務 console 只含啟動與 runtime 訊息，fixture 全文不寫入驗收結果；測試 DB 自身必然保存原文。

## M21／M22 邊界

以 [R2 原碼重播](../R2-memory-semantics/report.md) 與本次使用者明確指示為準。原 retrieval／update 仍是註解；query 為 prompt_info.strip() 後最後兩行 join，保留前導 newline；stored text 為最後一行，404 筆重播 strip 後相同；k=2。原四欄 human_question='None'、negotiation_result='None'、final_action='[id]'、comments=原 generate_comment 規則，不是假稱步後安全結果。

M21 才接 CAV prompt 檢索／呈現及完整 Qwen token 預算，不改 negotiation、原四欄或 M17 文字。M22 原版參考更新應為每車 LLM 回覆後、env.step 前；後車可讀前車同一步寫入，跨 episode 共用庫。M19 曾提步後寫入／固定快照，這是不同研究方法，不能偷偷採用或宣稱等價。本次只傳遞 caller 提供的原 query／text／metadata，不決定擷取或更新時機，不把測試 fixtures 寫正式庫。

目前尚不進 M21：須先取得本次 Spark 跨環境驗收證據。R6／R7 兩筆模板都不能證明交通相關性全面合格或 production memory on 完成；空資訊文字完全相同的上游限制仍存在。
