# M23 首次批次中止審查

2026-11-26，commit efc8a01d0196c90a77424e47952a3c10a3f94002，來源 `/home/nclab/Yizhen/runs/M23-intersection-memory-on-20seeds-Y6aiqi`，回傳 `runs/M23-review-n2o60wtb`。SHA256SUMS逐檔核對通過。這不是20seeds完成結果，不計算整批成功率。

seed0完成99步、396寫入，batch驗證記為all_arrived_inferred；其模擬秒數為19.733333，不能僅以99×0.2推定19.8（需保留實際ticks）。seed1從396筆開始，第0步完成四車回答與四筆寫入；第1步協商與車3回答／第五筆寫入完成，下一台車4在prepare→client.retrieve收到HTTP400，沒有送出車4action請求，也沒有執行第二次env.step。最終庫401筆，session正常關閉、final snapshot verified=true，快照 `4cf387ba43dbc389452665f8fc369118cb11778d1eee64602f4c69a5ef4c8e46`。

Qwen manager外層failed是project entry失敗的傳播；shutdown exit0、無已知殘留程序、port_closed=true、warnings=[]、clean_observation=true。目前直接證據是本機memory retrieve HTTP400，非已證明的斷線、OOM、Qwen生成或碰撞故障。現有資料沒有系統重啟／網路斷線紀錄，不能診斷使用者遠端重新連線原因。

服務把ValueError／KeyError／TypeError等映為400，且client隱去HTTP錯誤body、service未另記安全的細分診斷，故現有console不足確定是輸入／embedding／Chroma結果驗證哪一個分支。不能把400直接等同非法query，更不能自行修改向量範圍、token上限或回傳空候選繼續實驗。

原始DB、來源結果及部分寫入必須保留，不重新執行整批、不刪掉seed1紀錄或直接沿401筆重試seed1。下一步需隔離唯讀診斷與安全錯誤代碼，必要時使用既有個人DB唯讀開啟與失敗query重播（無Qwen／無sim步進／無add），確認原因後再設計有來源與失敗保留的恢復方式；目前沒有恢復實驗或宣稱已修好。
