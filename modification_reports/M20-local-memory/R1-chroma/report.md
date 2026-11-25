# M20-R1：保留 Chroma、替換本地 embedding

日期：2026-11-25。狀態：底層 adapter 與本地替身測試完成，Spark Chroma／真 embedding 尚待使用者手動驗證；未進入 M21。

## 2026-11-25 Spark 前置檢查回傳（M20-R1-05）

證據：[使用者提供的完整 console](../../../../spark相關console/memory%20on前置作業console.txt)。Spark 從 21799bd fast-forward 至 c486a54，qwen-local；更新前 status 沒有列出修改，並完成指定版本祖先檢查後續的盤點命令。

- Python 3.8.20，prefix／executable 均在個人 codriving-sim-py38；aarch64。
- SQLite 3.46.0 符合 Chroma 0.4.15 的 >=3.35.0 條件。
- 套件 metadata：numpy 1.24.4；chromadb、pydantic、chroma-hnswlib、posthog、langchain、torch、transformers、tokenizers、safetensors 皆為 null（該 interpreter 找不到 distribution metadata）。
- status=preflight_blocked，blocker 為缺少 chromadb==0.4.15。沒有執行真 Chroma round-trip，也沒有載入 embedding。
- 當時 RAM available 約 92 GiB；swap 已使用約 5.5 GiB；磁碟可用約 2.3 TiB。僅歷史快照，不能推論 GPU 現況、預留資源或未來可用量。

下一步調整：暫不執行下方原列第二步，不在已驗證模擬環境補裝 Chroma／LangChain，不改既有 Qwen 推論環境。先只讀盤點個人目錄內可用的 Python／環境管理工具，規劃獨立 memory 環境（Chroma＋CPU embedding）。若將 Chroma 放到獨立環境，模擬 Python 3.8 還需新增 memory HTTP 接線；目前只有 embedding HTTP，不能宣稱已有跨環境 Chroma 服務。此接線須補測後才能進 M21。此次只更新報告，沒有更動程式或遠端環境。

## 修改前與決定

使用者希望沿用原記憶架構，先正確儲存、檢索及基本相關性驗證，不擴大成 embedding 選型研究。M20 第一版已寫 MiniLM＋SQLite，但 SQLite 不是移除雲端 embedding 的必要條件，且會增加檢索後端變因。因此本次補上 Chroma backend，保留 SQLite 作精確搜尋參考。沒有刪除或覆蓋第一版測試證據。

Git 仍為 qwen-local／a669568cfbe07fef08dbd44d2b353c78bdba027d；開始時既有索引修改、M17–M20 及第一版程式未提交，全部保留。重新遞迴查無 repo AGENTS；未切分支、stash、commit 或 push。原作者 repo 與其 requirements.txt 未修改。

## 編號變更

### M20-R1-06：Python／工具盤點回傳與獨立環境準備

使用者回傳：PATH 可見 /usr/bin/python3、/usr/bin/python3.12；既有 Qwen interpreter 為 Python 3.12.3、SQLite 3.45.1，venv available=True，但該環境沒有 pip。command -v uv 未列出路徑，僅能判定目前 PATH 查不到，不能判定沒有安裝。

已從舊 [Spark Step2 console](../../../../spark相關console/spark%20linux基本資訊step2-console.txt) 查得 uv 曾安裝於 /home/nclab/Yizhen/bin/uv，版本 0.13.9。下一步直接以絕對路徑檢查工具，再用 /usr/bin/python3.12 建立全新的 /home/nclab/Yizhen/envs/memory-chroma0415-py312，執行 Chroma 相依 wheel-only dry-run；不替 Qwen 補 pip，不修改模擬／推論環境，不下載模型。該步尚未執行，不宣稱新環境已存在或 ARM64 wheel 已可用。

初步解析條件：chromadb==0.4.15、numpy==1.26.4、pydantic<2、posthog<4。後三者是預防舊 API 與 NumPy 2／Pydantic 2／新版 telemetry 相依不匹配的暫定約束，非已驗證 lock。wheel-only 解析若失敗，保留完整錯誤，不自動切換版本、編譯來源或執行全域安裝。uv cache／tmp／輸出均限個人目錄；目前只安排解析，未實際安裝 Chroma。

### M20-R1-07：新環境建立成功、wheel-only 解析被擋

使用者貼回 console：uv 0.13.9 使用 /usr/bin/python3.12（3.12.3）成功建立 memory-chroma0415-py312；相依 dry-run 因 chromadb==0.4.15 固定依賴 chroma-hnswlib==0.7.3，而目前平台無 usable wheels 被拒絕。此次沒有真 Chroma 安裝或測試證據；不能將錯誤解讀成虛擬環境建立失敗，也不能據此宣稱來源建置不可能。

下一個優先調查方向：維持 Chroma 版本，評估在新環境內從來源建置 chroma-hnswlib。先只讀檢查 C++ compiler 與 Python.h 是否存在；未確認前不執行 source build、不要求 apt／sudo、不更換為 SQLite。已查閱 [chroma-hnswlib 0.7.3 setup.py](https://github.com/chroma-core/hnswlib/blob/0.7.3/setup.py)，其擴充使用 C++、NumPy 與 pybind11。Python 3.12／ARM64 真實編譯與執行仍未驗證。此次只更新結果與下一步，未修改 backend 程式。

### M20-R1-08：來源建置前提具備

使用者回傳 /usr/bin/c++、/usr/bin/g++、/usr/bin/make，GCC 13.3.0；新 memory 環境 Python 3.12.3、include=/usr/include/python3.12、Python.h exists=True。確認具備基本工具，但 OpenMP link、pybind11 與實際擴充編譯尚未驗證。

下一步僅在新 memory 環境安裝暫定固定建置工具 numpy==1.26.4、setuptools==75.8.0、wheel==0.45.1、pybind11==2.13.6，再用該組工具無 build isolation 建置 chroma-hnswlib==0.7.3（不解析其餘相依），保存完整 console 與安裝清單。HNSWLIB_NO_NATIVE=1 避免套件預設的 -march=native；不加自訂安全／檢索門檻。以人工 384 維向量測試 cosine 索引的基本 add／query，成功後才能安排完整 Chroma 安裝。此步尚未執行，沒有真編譯成功證據。

### M20-R1-09：HNSW 來源編譯與人工向量測試通過

證據：[使用者 step2 console](../../../../spark相關console/memory%20on前置作業%20step2%20console.txt)。保存的命令貼上區有破碎顯示，因此不以該區重建完整 shell 命令；下列結論依實際套件安裝與測試輸出。

- 獨立 memory 環境安裝 numpy 1.26.4、pybind11 2.13.6、setuptools 75.8.0、wheel 0.45.1。
- chroma-hnswlib 0.7.3 來源建置成功，console 顯示 build 約 9.07 秒；模組載入位置為該環境 site-packages 的 hnswlib.cpython-312-aarch64-linux-gnu.so。
- 人工向量測試回傳 labels=[[10,20]]、distances=[[0.0,1.0]]，HNSW synthetic test: PASS。
- 遠端結果目錄 /home/nclab/Yizhen/runs/M20-R1-hnsw-build-NS3SOQ。

先前「沒有可用 wheel」的阻礙，已透過此次來源編譯繞過；目前沒有該建置失敗證據。人工向量只是用已知兩個 384 維單位向量核對索引新增與 cosine 查詢的基本行為，不含 MiniLM、不代表真文字相關性，也不是完整 Chroma 持久化測試。下一步為完整 Chroma 相依安裝／真 Chroma adapter round-trip，之後才準備 MiniLM 並檢查實際文字檢索。仍未進入 M21、未改 memory off 或原安全邏輯。

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
