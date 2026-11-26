# M23：intersection、20 seeds、原版語義 memory on

2026-11-26：使用者授權執行正式memory-on對照準備。程式及回傳整理工具完成，本地測試通過；Spark尚未執行。本報告不包含效果結果。

## 固定實驗條件

對照 [M18 off基線](../M18-intersection-memory-off-20seeds/report.md)：seeds0–19（seed0原M16、其餘M18），commit21799bdc2abc3b85d1c8562e90827e8287eeaf3d；不重跑off。該組9/20推定全車到達、7/20碰撞、4/20環境時間上限，seed17停服警告保留。

本次依序0→19各一次，全新experiment-chroma，第一seed空庫、後續共用累積。不得沿用M22驗收庫、seed間清空、重排順序或重試替換失敗。每seed沿用既有管理器啟停一個Qwen；memory服務保持同一個、同一writer。test_only=false表示正式資料，並不表示已驗證有效。

保留Qwen模型／revision、strict、300步／3600秒、原環境config與所有安全／速度邏輯。原四欄、generate_comment、k2、逐車步前寫入、空文字／重複記錄均維持；未套M17。新增 [baseline contract](../../validation/memory_on_baseline_contract.json) 由既有M16結果擷取，逐seed核對config／model／parser與步時上限。code commit必須乾淨且批次內一致。

## 編號

- M23-01：[run_memory_on_20seeds.py](../../validation/run_memory_on_20seeds.py) 新庫／20seeds順序、逐回合滾動快照與來源核對；batch-result即時保存完整／部分結果。碰撞或環境時間上限是有效交通結果，繼續下一seed；API／parser／memory／停服異常則停止，不自動重試或續跑。
- M23-02：[episode validator](../../validation/accept_memory_episode.py) 允許明確expected_seed、initial_records及test_only，既有R3預設不變。核對下一seed讀到所有較早seed資料，session計數只算本回合寫入；沒有將正式控制器新增實驗模式。
- M23-03：[collect_memory_batch.py](../../validation/collect_memory_batch.py) 只複製白名單證據與SHA256至新的M23-review目錄；排除DB、模型、cache，保留manager及episode同名結果的階層。失敗部分紀錄也可整理。
- M23-04：[shell入口](../../validation/run_memory_on_20seeds.sh) 建立Yizhen個人結果目錄，記錄資源與commit；EXIT時自動整理證據、保存原執行exit code，輸出原目錄及review目錄。沒有SSH、安裝、下載或Windows模型載入。

## 本地測試與限制

Windows Python3.13.13／PYTHONDONTWRITEBYTECODE=1。check_memory_batch3、check_memory_episode3、check_memory_live_step3、check_live_session13，共22項通過、四命令exit0。測試涵蓋後續seed非空共享庫、錯seed拒絕、來源候選核對、export白名單排除cache／DB、Python3.8 syntax、既有terminal／單步／啟停回歸。無新增套件，未在本地執行bash或真模型。baseline contract為唯讀既有結果擷取，Spark仍待驗。

完整snapshot/status每次可能掃描全庫，庫變大後耗時可能增加；目前沒有20seed成本數據，不預先宣稱效能。批次共享庫導致seed間依賴，結果僅代表固定順序的累積方法；與舊off的配對差異仍包含模型採樣／執行差異，不能直接當成唯一因果證據。

## 手動執行與回傳

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
df -h /home/nclab/Yizhen
ss -ltn 'sport = :18080 or sport = :18082'
# 乾淨qwen-local、兩port均無listener後執行一次，保持終端連線
bash validation/run_memory_on_20seeds.sh
```

最後輸出 `Review folder (copy this folder): /home/nclab/Yizhen/runs/M23-review-...`。整個review目錄回傳即可，原DB留Spark。包含root batch-result／config／commit／console／資源、service console、每seed console、每seed manager result／server-console／traffic-console，以及各episode result／review／全部step。SOURCE與SHA256SUMS自動建立。原完整庫是正式實驗資料，保留勿刪。

若自動整理失敗，可重新整理資料（不是重跑實驗）：

```bash
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python \
  validation/collect_memory_batch.py /home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-實際編號
```

中途失敗先回傳部分review與console，不直接重跑或換新庫跳過失敗seed。後續比較分開統計到達／碰撞／環境時間上限／執行失敗、模擬時間與步數、格式成功、檢索／寫入／token／啟停品質，與既有off逐seed配對；未完成時不以已成功子集計整批效果。
