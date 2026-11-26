# M23-R2：Chroma超額候選相容性修正

2026-11-26，回傳M23-R1-retrieval-diagnosis-uN3gb8。401筆庫原檔hash未變、副本count及snapshot前後一致（4cf387ba43dbc389452665f8fc369118cb11778d1eee64602f4c69a5ef4c8e46）。一個探測在adapter-search重現ValueError: Invalid Chroma query result shape。query hash 6fa65a36aadb3635e416d557bc4d95773435b670377e04f70b5a437b58fcb1e2，232chars。明確請求n_results=2，raw四欄卻各回3列，距離[1.1102230246251565e-16,0.002532482147216797,0.002532482147216797]，數值本身有效。

這支持原HTTP400的後端shape檢查原因鏈；因確切失敗query舊流程未保存，不能宣稱精確原請求重播，也未證明Chroma為何超額（不可將同距離直接當成已證明的tie bug）。與網路斷線沒有已知因果證據。

M23-R2-01：chroma_memory.search接受一致欄長且requested_size≤returned_size≤corpus_count；驗證全部回傳ID／文字／metadata／距離，再依既有score-desc與ID穩定排序，最後截取requested_size。仍最多2筆，不新增門檻、不改原四欄／安全公式、不忽略損壞資料。超額候選邊界相同分數時，取捨遵循現有排序，並非宣稱完全重現原雲端ranking。

M23-R2-02：新增替身回歸：3候選回2、超額第三筆NaN仍拒絕、欄長不一致仍拒絕。check_chroma_memory15項（真Chroma1項跳過）、check_memory_batch3、check_original_memory13；本地三命令完成，Spark真副本修正版待使用者手動驗收。未跑模型／sim／正式批次，未改401筆庫。現有diagnose_memory_retrieval可在全新副本重跑，仍只回傳diagnosis.json及console，不重跑seed0／seed1。

後續恢復須保留seed1失敗與5筆部分寫入，不直接從401筆重新跑seed1，也不自動刪除資料。先驗收相容性修正，再設計明確來源、版本與回合邊界的恢復流程。
