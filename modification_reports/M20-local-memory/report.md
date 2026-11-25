# M20：本地 embedding 介面與隔離記憶庫

2026-11-25 補充：使用者確認接續調整。正式後端方向改為本地 MiniLM＋Chroma；SQLite 保留作精確搜尋參考。本頁以下保留第一版歷史，最新狀態及測試見 [M20-R1 Chroma 報告](./R1-chroma/report.md)。仍未接入正式駕駛流程，未操作 Spark。

日期：2026-11-24。程式與本地替身驗證完成；Spark 真 embedding、套件安裝／ARM64 相容性及權重核驗尚待手動驗收。未接入正式駕駛流程，memory on 仍由現有 factory 拒絕，不能據此宣稱已完成 memory on。

## 基線與變更

分支 qwen-local，HEAD a669568cfbe07fef08dbd44d2b353c78bdba027d。開始前保留既有 README 索引修改、M17、M18、M19 未追蹤報告。repo 遞迴查無 AGENTS.md；延用 M19 已查父層結果。只新增本項檔案，未提交或推送 Git。

| 子項 | 新增內容 | 功能 |
|---|---|---|
| M20-01 | [local_memory.py](../../llm_controller/local_memory.py) | manifest、個人路徑檢查、loopback embedding client、SQLite store、文字層 LocalMemory adapter |
| M20-02 | [serve_local_embedding.py](../../validation/serve_local_embedding.py) | 使用者手動啟動的 Spark Linux CPU 服務；僅讀事先備妥的本地 snapshot，不下載模型 |
| M20-03 | [check_local_memory.py](../../validation/check_local_memory.py) | stdlib 替身、SQLite 與本機 HTTP 往返測試，無 ML 模型 |
| M20-04 | 本報告、[操作與架構說明](./architecture.md)、測試 console 與結果 | 記錄差異、證據及限制 |

沒有修改舊 memory.py、memory_mode.py、qwen_step.py、qwen_episode.py、主入口、vehicle_actions.py、安全 helper 或任何實驗原始結果；M17 prompt 修改未套用。

## 設計決定

- 官方模型候選定為 sentence-transformers/all-MiniLM-L6-v2，固定 revision 717413c64de70e37b55cf53c9cdff0e2d331fac3；384 維、attention mask mean pooling、L2 正規化、CPU。官方模型卡說明英文短文與語意搜尋用途，預設超過 256 word pieces 會截斷；本服務改為含 special tokens 超過 256 就拒絕，避免隱性丟失情境。這個模型的數字／交通情境檢索品質尚無實證。
- [固定 revision 官方模型卡](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/717413c64de70e37b55cf53c9cdff0e2d331fac3/README.md) 提供 mean pooling 與 normalize 範例。未下載任何檔案；模型卡查證不代表 Spark 權重核驗或套件支援已完成。
- 模擬端只使用 stdlib。服務端使用 torch／transformers／tokenizers／safetensors，但僅明確執行 Spark main 時才匯入／載入模型；不修改既有模擬或 Qwen 環境、不提供未驗證 pip 安裝命令。
- SQLite 存原文、metadata、向量；小資料庫採逐筆精確 cosine 搜尋，分數高者優先、同分按記憶 ID 排序，預設 top_k=2，沒有新增安全門檻。這與舊 Chroma 的分數／索引行為不等價。
- manifest 固定模型、revision、維度、pooling、正規化、長度與截斷政策、query schema、場景、距離方法及版本。服務／client／DB 必須一致；不自動遷移舊 Chroma。
- client endpoint 固定 127.0.0.1，只能選 port；停用 proxy、拒絕 redirect，無 fallback／自動重試。回覆核對 index、文字 SHA256、數量與有限非零 L2 向量。
- DB 新建需明確 create，拒絕覆蓋既有檔，既有庫預設唯讀；主鍵重複拋錯，不吞例外。metadata 必須有非空 source 物件，來源欄位的完整研究 schema 留待 M22。
- resolved path 限 /home/nclab/Yizhen 子目錄，含 symlink target。服務快取／暫存指定新 runtime 子目錄，CPU、offline、local_files_only、trust_remote_code=False、safetensors。服務記錄各 snapshot 檔案 hash、Python 與套件版本；資料庫另提供邏輯快照 SHA256。

## 本地測試

Python 3.13.13；依工具要求完成環境選取；PYTHONDONTWRITEBYTECODE=1。無模型下載／載入、無雲端請求、無交通模擬、無 Spark 操作。HTTP 測試只啟動 Windows loopback 的臨時埠，使用人工單位向量，測完立即停止。

| 測試 | 結果 |
|---|---|
| check_local_memory.py | 16 項：15 通過、1 略過；資料往返／來源保存、cosine 與同分排序、空庫、錯誤 k、重複 ID、唯讀／不隱性建庫、不覆蓋、manifest 不符、壞向量、路徑越界、text adapter、HTTP 往返、回覆順序／hash、proxy／redirect、Python 3.8 語法與不匯入 ML |
| check_memory_off.py | 5/5 通過，on 仍拒絕、off 不觸及舊雲端記憶依賴 |
| check_vehicle_actions.py | 13/13 通過 |
| 編輯器 diagnostics | 三個新增 Python 檔皆無錯誤 |

symlink 測試因 Windows WinError 1314 無建立連結權限而略過，不冒稱通過。正式 personal_path 實作有 resolve 檢查；Linux symlink 測試留給 Spark。

重現命令（repo 根目錄、既有本地 Python）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/user/miniconda3/python.exe' validation/check_local_memory.py
& 'C:/Users/user/miniconda3/python.exe' validation/check_memory_off.py
& 'C:/Users/user/miniconda3/python.exe' validation/check_vehicle_actions.py
```

## 待驗與限制

- Python 3.8 目前只有語法相容檢查，真正 3.8 執行、Spark ARM64 套件與真模型推論尚未測試；本地 3.13 通過不能替代它們。
- 服務要求 snapshot 目錄名稱是 revision，並保存實際檔案 hash，但目錄名稱與自算 hash 不能證明來自官方。啟動前仍需將固定 revision 下載來源及 hash 對照核驗，禁止把改名資料夾當成已核驗模型。runtime.json 用於證據盤點，非自動驗真機制。
- 256 token 拒絕邏輯已實作，真 tokenizer 邊界／pooling 數值一致性待 Spark 驗收。
- HTTPServer 是單請求序列服務，適合目前序列小規模測試；同一共用帳號／主機的 loopback 不提供身分隔離，無權限保證或服務認證。HTTP 有請求上限與 socket timeout，但模型 CPU 推論沒有獨立的強制終止時間。
- SQLite 精確搜尋為 O(N×384)，不適合未經量測的大型記憶庫；本項沒有 ANN 效能承諾。快照應在寫入停止後取得；跨程序同時寫入的實驗快照管理留待 M22。
- 未啟用正式記憶，不變更 query 擷取、prompt 注入、更新時機、成功資料篩選、風險計算或速度控制。這些分別留待 M21／M22；M23 才由使用者手動驗收真實整合。
