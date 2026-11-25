# M20-R1：保留 Chroma、替換本地 embedding

日期：2026-11-25。狀態：底層 adapter 與本地替身測試完成，Spark Chroma／真 embedding 尚待使用者手動驗證；未進入 M21。

## 修改前與決定

使用者希望沿用原記憶架構，先正確儲存、檢索及基本相關性驗證，不擴大成 embedding 選型研究。M20 第一版已寫 MiniLM＋SQLite，但 SQLite 不是移除雲端 embedding 的必要條件，且會增加檢索後端變因。因此本次補上 Chroma backend，保留 SQLite 作精確搜尋參考。沒有刪除或覆蓋第一版測試證據。

Git 仍為 qwen-local／a669568cfbe07fef08dbd44d2b353c78bdba027d；開始時既有索引修改、M17–M20 及第一版程式未提交，全部保留。重新遞迴查無 repo AGENTS；未切分支、stash、commit 或 push。原作者 repo 與其 requirements.txt 未修改。

## 編號變更

| 編號 | 檔案 | 內容 |
|---|---|---|
| M20-R1-01 | [chroma_memory.py](../../../llm_controller/chroma_memory.py) | 延遲載入、固定 Chroma 0.4.15，新增／搜尋／snapshot；沿用 LocalMemory 文字 adapter |
| M20-R1-02 | [check_chroma_memory.py](../../../validation/check_chroma_memory.py) | API 替身測試與明確 Spark-only 真 Chroma 人工向量測試開關 |
| M20-R1-03 | [inspect_memory_runtime.py](../../../validation/inspect_memory_runtime.py) | Spark 只讀套件 metadata／SQLite 版本盤點，不匯入 Chroma／ML、不安裝 |
| M20-R1-04 | 本報告、既有 M20 頁面狀態註記、報告索引 | 保留歷史並指出新的正式後端方向 |

## 架構與原版差異

```text
情境文字
  → LocalMemory
  → LocalEmbedding（127.0.0.1 HTTP）
  → Spark CPU MiniLM（M20 第一版服務，真模型尚待驗）
  → 明確提供 embeddings 給 ChromaMemoryStore
  → 個人目錄內全新的 Chroma collection
  → 原文、來源 metadata、ID、cosine distance、score
  → M21 才接 action prompt
```

原 memory.py／LangChain helper 保留不動，新 backend 直接使用原 requirements 指定的 chromadb==0.4.15 公開 API；不需用 LangChain 重包，不會匯入 OpenAIEmbeddings。建立及開啟 collection 都明確 embedding_function=None；新增與查詢都提供已驗證的向量，禁止 Chroma 自動選預設 embedding 或下載模型。

已核對 [0.4.15 Collection API](https://github.com/chroma-core/chroma/blob/0.4.15/chromadb/api/models/Collection.py) 與 [PersistentClient](https://github.com/chroma-core/chroma/blob/0.4.15/chromadb/__init__.py)。這是 API 原始碼查證，不等於 Spark 相依已通過。

固定 manifest 與 collection metadata 包含模型／revision／query schema／scene、維度、pooling、正規化及 metric。新建目錄必須不存在；開啟前核對目錄 manifest，且 collection metadata 必須相符。外部庫／舊 OpenAI 向量不遷移、不混用。source metadata 以 JSON 字串封裝，避免 Chroma 0.4.15 的扁平 metadata 限制；目前不提供內層 source 的 Chroma where 篩選。

本次保留 M20 cosine 設定，回傳 distance 及 score=1-distance，不作安全門檻。原作者未明確設定 cosine，故本項不能宣稱保留原庫的所有排序行為。對完全正規化向量，精確 squared-L2 與 cosine 的理論排序一致；HNSW 近似搜尋及邊界同分仍可能不同。只對回傳候選做穩定排序，不承諾全庫同分選出的集合固定。SQLite 參考測試使用同一批人工向量核對排序，但不是實際 Chroma 索引召回率驗證。

新增前檢查重複 ID，新增後 get 核對原文／metadata／向量，不讓舊版 Chroma 忽略重複資料卻被誤報成功。寫入程序以 writer.lock 排除本 adapter 的其他 writer；錯誤向外傳遞，不盲目重試。程序異常終止可能留下 lock，由使用者確認無活躍 writer 後處理，不自動清除。鎖只能協調使用本 adapter 的寫入者，不能阻擋其他程式直接改庫。

預設唯讀是 adapter 層拒絕 add，**不是檔案層唯讀**：PersistentClient 開啟時仍可能建立／更新內部狀態。因此正式比較應使用獨立凍結副本並停止 writer；本項不以此冒稱原始 Chroma 快照完全不被觸碰。close 釋放本 adapter writer lock，不呼叫 Chroma 私有 shutdown，也不承諾卸載內部 client／索引；真服務的生命週期仍待整合。

遠端路徑使用現有 personal_path，限制 resolved path 在 /home/nclab/Yizhen；Chroma telemetry 設為關閉，不改全域設定。Spark 指令將額外快取／暫存放個人目錄。正式控制模組不 import 新 backend，memory off 無新增開庫、請求或模型載入。

## 本地測試與證據

既有 Python 3.13.13，PYTHONDONTWRITEBYTECODE=1；不安裝套件、不匯入真 Chroma、不載入模型、不呼叫雲端、不啟動 Qwen、不執行模擬。

| 檢查 | 結果 |
|---|---|
| check_chroma_memory.py | 13 項，12 通過、1 略過（真 Chroma 僅手動 Spark 執行） |
| check_local_memory.py | 16 項，15 通過、1 略過（Windows 無 symlink 權限） |
| check_memory_off.py | 5/5 通過 |
| check_vehicle_actions.py | 13/13 通過 |

本次新增測試涵蓋向量明確傳入、embedding_function=None、原文與來源往返、distance／score、空庫／小庫、重複 ID、manifest／metric 不符、唯讀 API、writer lock、失敗釋鎖、錯誤結果拒絕、SQLite fixture 排序、LocalMemory 接線、延遲匯入與 Python 3.8 語法。共 45 通過、2 略過，不是 47 項全通過。測試 console、逐項 exit code 與 source SHA256 見本目錄保存檔。

## Spark 下一步（使用者手動）

先將新增檔案與第一版 local_memory／check_local_memory／serve_local_embedding 同步至個人 repo；本次尚未 commit／push，不能假設遠端已有。以下在 Spark repo 根目錄執行，使用既有模擬 Python；不載入模型、不重部署 Qwen、不重跑任何交通 seed。

### 第一步：只讀相依盤點

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/inspect_memory_runtime.py
```

請回傳完整 JSON。預期至少 chromadb=0.4.15、SQLite>=3.35.0；ready_for_synthetic_chroma_test 只代表 metadata 門檻符合，不能替代 import／ABI 驗證。若不符先保留結果，不自動安裝或升級既有環境。

### 第二步：相依盤點符合後，真 Chroma＋人工向量

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
mkdir -p /home/nclab/Yizhen/runs/M20-R1-chroma/tmp /home/nclab/Yizhen/runs/M20-R1-chroma/cache
set -o pipefail
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/nclab/Yizhen/runs/M20-R1-chroma/tmp XDG_CACHE_HOME=/home/nclab/Yizhen/runs/M20-R1-chroma/cache /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/check_chroma_memory.py --real-chroma 2>&1 | tee "/home/nclab/Yizhen/runs/M20-R1-chroma/chroma-synthetic-$(date -u +%Y%m%dT%H%M%SZ).console.txt"
```

預期 13 項通過；任何 import／numpy／pydantic／hnswlib 錯誤請保留完整 console。此步使用暫存的新庫與人工向量，不碰既有 Chroma 或 M18 原始結果。測完程序退出；不需保持服務運行，也不需啟動 embedding／Qwen。

### 第三步：盤點後另備真 embedding

尚待固定 MiniLM snapshot 來源／hash 核驗、專用 embedding 環境相依與 CPU 推論證據。不能將本地替身測試當成真檢索相關性驗證。此階段完成後，才做小組英文交通案例查詢及人工相關性審查；不把 memory 成敗直接當成 Qwen 效果。底層通過後才接 M21 prompt 注入，寫入時機留在 M22。

## 保留邊界

未變更 memory_mode、qwen_step、qwen_episode、主入口、vehicle_actions、legacy agents、安全公式／門檻／優先權／signed distance／速度處理。未套用 M17 prompt 修改。M18 20 seeds 基線完整保留。
