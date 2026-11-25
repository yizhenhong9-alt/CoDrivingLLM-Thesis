# M20-R4：MiniLM CPU 相依規劃與 Chroma 基線保護

日期：2026-11-25。狀態：規劃工具及本地 6 項測試通過；Spark 解析待使用者手動執行。沒有安裝 embedding 相依或下載／載入 MiniLM。M20-R3 已由 step3 console 確認真 Chroma 14/14 通過，此次不重跑已通過項目。

## 編號與範圍

- M20-R4-01：[plan_minilm_runtime.py](../../../validation/plan_minilm_runtime.py) 核對個人 memory interpreter、ARM64／Python 3.12，以及當前套件是否與上次通過的 packages-after.txt 完全一致。只用 stdlib metadata，不匯入 Chroma／ML。
- M20-R4-02：[plan_minilm_runtime.sh](../../../validation/plan_minilm_runtime.sh) 保存套件約束、CPU wheel 來源、dry-run console 與 RAM／磁碟快照；只規劃，不執行 uv 安裝。
- M20-R4-03：[check_minilm_plan.py](../../../validation/check_minilm_plan.py) 使用人工 HTML／套件清單驗證版本、平台、來源、hash 及 baseline 拒絕條件。

保留 qwen-local、既有未提交的 R3 實測補記。沒有修改原作者 repo、requirements、Qwen／模擬環境、prompt、memory 生產介面、安全公式／門檻／優先權或速度處理。

## 暫定相依候選

使用 PyTorch 2.9.1+cpu 官方 CPython 3.12／manylinux_2_28／aarch64 wheel，Transformers 5.22.2，以及由解析器選擇相容版本的 safetensors。不是最後 lock，實際相容性須以 Spark dry-run、後續 import 與真模型推論證明。

查證來源：[PyTorch 官方 CPU wheel index](https://download.pytorch.org/whl/cpu/torch/)、[Transformers 5.22.2 PyPI metadata](https://pypi.org/pypi/transformers/5.22.2/json)。前者列出 2.9.1+cpu 的 cp312 aarch64 wheel；後者是已核對存在的套件版本，也與既有 Qwen 環境的 Transformers 版本一致，但新環境不共用 Qwen 的 CUDA torch。MiniLM 推論只需要 AutoTokenizer／AutoModel 與既定 pooling，不引入 sentence-transformers 訓練／評測工具鏈。

規劃時從官方 CPU index 選擇唯一符合檔名、HTTPS 官方主機、sha256 fragment 的直接 wheel URL，避免一般 torch 解析引入 CUDA／NVIDIA 相依。uv dry-run 仍可能下載套件中繼資料／wheel 到個人 cache；不等於完全沒有網路或套件下載，但不安裝套件、不下載任何模型權重。

以 /home/nclab/Yizhen/runs/M20-R3-chroma-ziPNpa/packages-after.txt 作為已通過的套件基線，先確認當前 distributions 完全一致，再將每個已安裝套件寫成 exact constraints。若新的相依不相容，直接報錯，不放寬約束、不自行降版 tokenizers／huggingface-hub／numpy。dry-run 後再次 freeze 比對，確保版本未改；這是版本清單檢查，不代表所有檔案已做完整 hash 核驗。

## 本地驗證

Python 3.13.13 stdlib，PYTHONDONTWRITEBYTECODE=1；check_minilm_plan.py 6/6 通過：正確官方 wheel、錯誤平台／版本拒絕、非官方主機／缺 hash 拒絕、不同 wheel 來源歧義拒絕、exact baseline 解析與重複／寬鬆 pin 拒絕、不匯入 ML／Python 3.8 語法。編輯器對兩個新增 Python 檔無 diagnostics。

本地測試沒有實際 fetch index、執行 uv dry-run 或驗證 Bash 執行；官方資料另由瀏覽工具查證。console 與 source hash 見本目錄。SHA256 欄位存在驗證不等於本地已下載並核驗 wheel bytes；真正的下載完整性由後續安裝工具依 URL hash 檢查。

## Spark 手動執行

同步 Git 後執行：

```bash
bash /home/nclab/Yizhen/src/CoDrivingLLM-Thesis/validation/plan_minilm_runtime.sh
```

預期最後顯示 `M20-R4 plan: PASS; package baseline unchanged; no model downloaded or loaded.`，並列出 /home/nclab/Yizhen/runs/M20-R4-minilm-plan-* 結果目錄。請保存／回傳 preflight 與 dependency-plan console，以及 plan.json；若缺基線檔案、當前版本改動、官方 wheel 不存在或解析衝突則停止，保留原錯誤。

此步不啟動服務、不用 GPU、不需 GPU 埠盤點。CPU embedding 真啟動前仍需重新查看資源；目前記錄的 RAM／磁碟只是執行當下快照。

## 後續

解析通過後才安裝到第三個環境，驗證 imports／CPU torch／Chroma 回歸，再下載 MiniLM 固定 revision 並核對來源、大小／hash；之後才用原 memory 模板文字測真向量、metadata 往返與檢索相關性。仍不進入 M21，也不重跑 20 seeds。
