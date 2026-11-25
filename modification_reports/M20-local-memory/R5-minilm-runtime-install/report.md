# M20-R5：安裝已解析的 CPU runtime 與回歸驗收

日期：2026-11-25。狀態：安裝／驗收腳本與本地 guard 測試完成；Spark 安裝與 imports／CPU tensor／Chroma 回歸尚待使用者手動執行。沒有下載／載入 MiniLM，沒有進入 M21。

## Spark 實測補記（M20-R5-04）

建立報告時的待執行項目，已由 [使用者 step5 console](../../../../spark相關console/memory%20on前置作業%20step5%20console.txt) 驗證。Spark 版本 6372f98eb068d5f9a7774b4f1d0e56ff4904173b；結果目錄 /home/nclab/Yizhen/runs/M20-R5-minilm-runtime-jhL8nq。

- before／after／runtime 三階段 status=PASS；原 80 個套件版本保持不變，新增固定 9 個套件。
- pip check：Checked 89 packages，All installed packages are compatible。
- torch=2.9.1+cpu，cuda_build=null，device=cpu；2×2 tensor 結果 [[7.0,10.0],[15.0,22.0]] 正確。
- AutoModel／AutoTokenizer／BertModel／safetensors 匯入成功；沒有實例化 pretrained 模型。
- Chroma 回歸 14/14 全部通過（1.955 秒），含跨程序重開及原 metadata 欄位對照。最後 runtime: PASS，exit 0。
- MiniLM 權重仍未下載／載入，沒有 CPU embedding 延遲與真實文字檢索品質證據。當時 RAM available 約 92 GiB、磁碟可用約 2.3 TiB，僅快照。

環境建置階段到此通過，不再重做相同安裝。M20 剩餘兩個驗收範圍為：固定 revision 權重核驗＋真 embedding／Chroma 原模板往返與相關性，以及跨環境 memory service HTTP 接線驗證。前者可合併下載後的離線測試，後者需程式實作；不能把現有 embedding-only HTTP 誤稱已完成 memory service。M21 prompt 注入、M22 更新流程及 M23 真 Qwen 短程驗收仍未完成。

## 基線與編號

R4 step4 console 已確認 dry-run 成功、80 個 Chroma baseline 套件維持原版本，新增 9 個套件相依可解析。遠端規劃目錄 /home/nclab/Yizhen/runs/M20-R4-minilm-plan-EbHo7u。本次不重新選版本、不重做 HNSW 編譯。

- M20-R5-01：[verify_minilm_install.py](../../../validation/verify_minilm_install.py)：安裝前核對原 baseline 的檔案 hash、constraints 與目前版本清單；安裝後只接受原 80 個版本＋指定 9 個套件；Spark runtime 階段才匯入 torch／transformers／safetensors。
- M20-R5-02：[install_minilm_runtime.sh](../../../validation/install_minilm_runtime.sh)：第三個環境專用手動腳本，採 PyTorch 官方 CPU wheel 直接 URL＋SHA256、exact 新套件版本、原 constraints 與 --no-build，不執行新的來源建置。
- M20-R5-03：[check_minilm_install.py](../../../validation/check_minilm_install.py)：本地 stdlib guard 測試，無安裝／ML 匯入。

新增版本完全依 step4 console：torch 2.9.1+cpu、transformers 5.22.2、safetensors 0.8.0、jinja2 3.1.6、markupsafe 3.0.4、mpmath 1.3.0、networkx 3.7、regex 2026.11.23、sympy 1.14.0。不是將現有 Qwen CUDA torch 複製進來。CPU wheel hash=3bf9b442a51a2948e41216a76d7ab00f0694cfcaaa51b6f9bcab57b7f89843e6，與 R4 plan.json 必須相符。

## 驗收流程

1. 檢查個人 memory interpreter 與原 80 個 distributions 完全一致，產生 exact install requirements。
2. 僅對 memory-chroma0415-py312 安裝這 9 個套件；uv 下載套件，不下載模型權重。
3. pip check、安裝後 distributions exact 比對與 freeze 保存。
4. CPU-only torch 驗證（torch.version.cuda is None），單執行緒 2×2 tensor 乘法；匯入 AutoTokenizer、AutoModel、BertModel、safetensors。不呼叫 from_pretrained，不建立任何模型。
5. 因新相依可能影響既有功能，再執行一次 check_chroma_memory.py --real-chroma，確認 14 項含跨程序重開均通過；不是無變更下重複測試。

輸出固定在個人 runs/M20-R5-minilm-runtime-*，cache 沿用個人 R4 cache；HF_HOME、TORCH_HOME、XDG、TMP 均在個人目錄。設定 offline、CUDA_VISIBLE_DEVICES 空值與單 CPU thread；無 Qwen 啟動、GPU 操作或其他人程序處理。

此腳本對 partial install 明確停止，不自動重跑／補裝／回滾。如果前一輪安裝成功但 runtime 檢查失敗，重新跑會在 before guard 拒絕；請保留 console 另查，不刪環境。版本核對不是全環境 byte-level 完整性驗證，也不代表真模型品質。

## 本地測試

Python 3.13.13 stdlib、PYTHONDONTWRITEBYTECODE=1；check_minilm_install.py 5/5 通過，涵蓋 before／after 預期集合、原版本變更／額外套件拒絕、CPU wheel 版本／hash 與 exact pins、缺套件／錯版本及部分安裝拒絕。不匯入 ML、Chroma，不安裝套件。兩個新增 Python 檔編輯器無 diagnostics。

console 與 source SHA256 保存於本目錄。Bash 只有靜態審查，真正腳本執行與模型介面匯入尚待 Spark 證據。此次保留已回傳 R4 實測補記；正式 memory off、原作者 repo、安全公式／門檻／優先權／速度處理與 M17 prompt 全部未改。

## 使用者手動執行

同步本次 Git 後：

```bash
bash /home/nclab/Yizhen/src/CoDrivingLLM-Thesis/validation/install_minilm_runtime.sh
```

預期：pip check 成功、before／after／runtime JSON 的 status=PASS，安裝後共 89 個套件、CPU tensor 結果 [[7,10],[15,22]]、cuda_build=null，以及 Chroma 14/14 OK，最後印 M20-R5 runtime: PASS。任何失敗保留完整 console 與印出的結果目錄，不自行移除限制或升級其他環境。

此步不需查 GPU 埠；腳本會保存當下 RAM／磁碟資訊。成功後才安排 MiniLM 固定 revision 下載、來源／hash 核對、CPU 真 embedding、原模板相關性與延遲量測。
