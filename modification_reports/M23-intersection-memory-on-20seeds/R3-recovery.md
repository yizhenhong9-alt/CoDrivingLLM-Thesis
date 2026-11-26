# M23-R3：保留失敗證據、恢復seed0邏輯邊界並續跑

2026-11-26，使用者授權繼續。R2 Spark副本19組全PASS，原超額候選仍回3筆但adapter正常回2；原401筆庫hash不變，前後snapshot一致。此為修正驗收，不代表19seed完成。

## 編號與範圍

- M23-R3-01：[recover_memory_batch.py](../../validation/recover_memory_batch.py) 只支援已審查efc8a01原失敗批次。驗證seed0完整證據396筆、seed1五筆已verified且無不確定寫入、停服乾淨。原DB只做檔案hash與copy，不由Chroma開啟；writer.lock存在拒絕且不刪除。副本獨立writer鎖、401筆ID集合及snapshot必須符合失敗證據，才在副本精確delete該5個ID。恢復count396及snapshot必須等於seed0邏輯邊界。原DB前後逐檔hash核對，產生recovery.json。
- M23-R3-02：[batch runner](../../validation/run_memory_on_20seeds.py) 新增明確--recovery-source，必須有ready recovery receipt；seed0列為retained-original-seed0並標原commit，從1→19繼續。seed1標retry-after-retrieval-fix，之後first-attempt。既有新批次行為維持0→19，不能把此resume泛用於其他中斷點。保留原attempt，不替換失敗紀錄。
- M23-R3-03：[memory_service_session.py](../../validation/memory_service_session.py) 顯式writable開啟既有已恢復副本，預設不變；其啟動後count與snapshot再次檢查。原四欄、heuristic、逐車步前寫入、k2、安全公式與速度處理不變。
- M23-R3-04：[exporter](../../validation/collect_memory_batch.py) 增加recovery與preparation console，以及prior-attempt證據白名單。新結果保留seed0選定原檔、原seed0和失敗seed1全部選定資料；不複製模型／DB／cache到review。
- M23-R3-05：[resume shell](../../validation/resume_memory_on_20seeds.sh) 建立全新recovery目錄，先以既有memory Python執行無模型的副本恢復，再由sim Python啟動批次。準備失敗不啟動Qwen，不自動重試；EXIT自動整理review並保留code。

## 可比較性與限制

原始401筆庫永久保留；移除只發生在新副本，不修改source或原作者副本。使用delete恢復的是文件／metadata／向量的邏輯快照，不能宣稱HNSW實體索引逐位元等於seed0當時；候選邊界的tie可能仍受index影響。seed0使用舊commit保留，後續修正版為新commit，原失敗seed1仍列為技術失敗，必須在實驗結果交代這個版本／恢復差異，不當作同一commit無中斷的20回合。seed1重試是本次明確恢復操作，不是刪除失敗後挑成功結果。

沒有重跑seed0或off20seeds。尚未在Spark驗收restore或續跑完成；receipt不ready或snapshot不同則停止，不放寬檢查。庫累積時status全庫snapshot耗時可能增加，沒有20seed效能保證。

## 本地測試

Windows Python3.13.13、stdlib／FakeChroma、無ML／sim／模型載入、無新增套件。check_memory_recovery4、batch3、episode3、live_step3、Chroma15，共28項中27通過、真Chroma1跳過，五命令exit0。驗證只刪失敗ID並恢復原snapshot、錯snapshot／未知ID在delete前拒絕、prior-attempt匯出而排除DB、Python3.8 syntax與既有回歸。編輯器診斷、git diff --check另核對。未本地執行bash／Spark程序。

## 手動執行與回傳

先pull乾淨qwen-local，確認18080／18082無listener，原始失敗批次沒有程序在寫入。執行一次resume shell即可先恢復後續跑；不使用舊run_memory_on_20seeds.sh。來源固定 `/home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-Y6aiqi`。

長實驗可用nohup（無新套件）把launcher stdout/stderr寫到Yizhen新目錄，將PID保存；斷線重連後tail同一launcher-console，不再次啟動。nohup不處理機器重啟、OOM或程式錯誤。

結束後launcher log印出Review folder，整個M23-review資料夾回傳，包含recovery.json、preparation-console、batch-result、原失敗attempt與保留seed0、每seed全部step與兩層result、console與hash；原庫／恢復庫留Spark。失敗先回傳部分資料，不重新啟動resume，因新失敗可能有更多部分寫入且此恢復工具不適用其他邊界。
