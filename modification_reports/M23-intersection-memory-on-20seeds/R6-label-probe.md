# M23-R6：一次seed1零步進名稱探測

## Spark 回傳審查（2026-11-26）

來源 `/home/nclab/Yizhen/runs/M23-R6-label-probe-OrT4ih`，capture `20261126T072139Z-dc96e77e.json`，git_commit=75c7072823127f8f14ab2df2b1375d82fc418c66。這次fixture探測確實在同一guard停止，且成功留下真實重複者：simulation_id3的Python object id=275988742030624、simulation_id6的Python object id=275988742848624；兩數不同但除1000的餘數都為624，兩車同屬MDPVehicle，故都顯示MDPVehicle #624。這是Spark本次實例，不是先前Windows物件示範；也不能倒推它們就是上次恢復失敗的重複者。

其餘road名稱為IDMVehicle #96／#264／#768、MDPVehicle #720／#464，本次重複分組只有#624。calls=[]、actual_environment_steps=0，未呼叫Qwen、未檢索／寫memory或執行env.step；exit1是保留guard拒絕的預期診斷結果，不是診斷未取得資料。正式396筆恢復庫與401筆原庫未由此工具開啟。

結論：物件識別值取餘數造成同class名稱重複已獲本次直接證據。交通simulation_id3與6仍不同，不能稱正式ID重複，也不是交通碰撞。命名修正尚未套用；不能刪guard、只改LLM names或用反覆重試挑無撞名執行。下一步如授權修正，需整條字串比對鏈一致、獨立編號及回歸，記錄prompt名稱與舊off基線可比性限制。

2026-11-26使用者要求再跑一次檢查是否同問題，並詢問餘數重複實例。提供Spark手動probe_vehicle_labels.sh，seed1一次fixture初始化／原安全helper與prompt流程，無真Qwen／memory HTTP／DB、無env.step，不重跑正式episode。與memory-on程序配置路徑不同，不能稱原失敗配置精確重播；通過只代表此新程序沒有碰撞，不能證明不再發生。不反覆重試挑成功。

M23-R6-01：qwen_step將原有vehicle_identifiers提前至guard前保存；碰撞時額外保存legacy_label分組及simulation_id、Python object id與%1000。保留原guard拒絕，未改命名、prompt或安全公式。非碰撞時僅提前同一欄位的賦值，沒有修改原決策流程。

M23-R6-02：新增替身測試強制兩個不同物件同label，確認persist後拒絕、無呼叫／步進。這是人工模擬guard回歸，不聲稱實際物件%1000等於該模擬label。真餘數碰撞由Spark實際紀錄確認。

數學例：123456%1000=456、987456%1000=456；完整整數不同不保證餘數不同。這兩個數不是實驗中已觀測的Python object id。Vehicle.__str__用相同class加該餘數，可能同名；與simulation_id及交通seed不同。

本地只跑stdlib替身及既有回歸，Spark實際初始化仍由使用者手動。回傳新probe目錄的git-commit.txt、console.txt與capture/*.json，不需cache。無撞名也如實保存，不直接恢復正式批次。

本地check_qwen_single_step15項及check_memory_batch3項全PASS、exit0；不載入sim／模型。另可用同時保留1001個object的stdlib實驗，找出兩個不同id取%1000相同；這是Python命名設計示範，不是Spark失敗車輛的取證。
