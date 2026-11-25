# M22-R3：單一seed完整memory-on回合整合驗證

## Spark 回傳完整審查（2026-11-25）

實際 commit `23d53b6e28b7c23e8228838ca02e4678e17559de`，來源 `/home/nclab/Yizhen/runs/M22-R3-memory-episode-qHV6Ij`；使用者console PASS／exit0。回傳 `runs/M22-R3-review-vWvyDf` 全部齊全：SHA256SUMS列出的112個檔案均hash相符，無清單外遺漏／多餘檔（清單本身另計），manager及episode結果各一份，step-0000至0098連續99份。已執行 [audit_spark.py](./audit_spark.py) 得PASS，結果與逐檔hash保存於 [spark-audit.json](./spark-audit.json)。以下「尚未執行」為歷史狀態，以本節更新。

### 流程與記憶

- 99步、396查詢／396筆verified寫入、495真Qwen呼叫（99協商＋396action），全部strict重新解析通過；API回覆內容、finish_reason=stop與token usage核對一致。server console恰有495次chat POST200。
- 每步四車query前庫筆數依序4t至4t+3，庫由0累積至396，唯一ID、原metadata、候選對應先前寫入、query／候選／完整prompt hash、receipt與跨步snapshot鏈核對通過。session 891次token_checks，正常關閉且最終snapshot一致。
- 最大輸入1093tokens，加保留輸出256為1349≤2048；沒有記憶因長度排除。候選總數789（0＋1＋394×2），其中17個候選來自同一步較早車的寫入；這是candidate次數而非17個step，保留原逐車步前可見性。
- 動作總數：SLOWER2、FASTER321、IDLE73。這是輸出分布，不能據此判定最佳性或歸因memory。
- 357／396（90.15%）筆stored text是空衝突文字，396筆只有18種不同stored text；ID仍各自獨立，不去重、不篩除。庫筆數增加不等於資訊多樣性提高，embedding不能還原未輸出的交通資訊。

### 回合結果與終止解讀

99步×0.2秒＝19.8模擬秒（297 physics ticks）。全部步進的info.cav_crashed與四車final crashed皆false，最後done=true、agents_dones四個true、reward1；逐步reward合計30.5。episode_terminal是自然終止，沒有碰到300步或3600秒上限。

依 [原環境終止規則](../../../highway_env/envs/intersection_env.py)，全域done可能由CAV碰撞、四車到達、環境duration×policy_frequency−1、或啟用的offroad終止觸發。這次99步小於50×5−1，offroad_terminal=false，無CAV碰撞，而agent terminal在未逾時且未碰撞時僅剩has_arrived，因此可由紀錄與程式條件推論四車到達。回傳沒有獨立has_arrived欄位，這是條件推論；不等於所有背景車都無碰撞（原環境有背景車清理），也不等於多seed安全保證。

Qwen shutdown exit0、remaining_known_processes=[]、port_closed=true、clean_observation=true，與console正常停服一致；warnings=[]只針對管理器特定停服警告，不代表無啟動警告。API action呼叫時間中位0.367秒、最大1.176秒；negotiation中位0.194秒、最大30.629秒。這些不是純embedding／檢索延遲，不能當memory效能基準。

### 結論與邊界

M22-R3單seed完整回合整合驗證通過，原逐車寫入在跨步累積後仍能接上真Qwen與步進。沒有重新跑memory-off、沒有配對控制或多seed比較，不能宣稱memory提高安全、效率或到達率，也不能把99步相對先前回合差異歸因memory。未修改控制器、原四欄／heuristic、寫入時機或預設off；尚未自動開始正式多seed實驗。

2026-11-25：M22-R2單步與manager補件審查PASS後準備；Spark尚未執行。這不是正式多seed效果實驗。

## 編號與邊界

- M22-R3-01：[episode驗收器](../../../validation/accept_memory_episode.py) 沿用R2全新空庫、同一memory服務及既有Qwen啟停管理器，只跑seed0、max_steps300、wall_seconds3600，要求episode_terminal與最後done=true才PASS。碰撞也可能terminal；PASS表示流程驗證，非安全到達。
- M22-R3-02：[R2共用流程](../../../validation/accept_memory_live_step.py) 新增內部episode參數，預設仍單步；R3保存全部step_reports路徑，檢查跨步候選來源、滾動snapshot/count、原四欄、ID／寫入hash與session最後狀態。原正式控制器、off/on語義與安全處理均未改。
- M22-R3-03：[shell入口](../../../validation/accept_memory_episode.sh) 保存console／commit／資源；只在 `/home/nclab/Yizhen/runs/M22-R3-memory-episode-*` 新建庫與服務暫存，不沿用R1/R2測試資料或重跑20seed基線。
- M22-R3-04：[本地gate測試](../../../validation/check_memory_episode.py) 驗證terminal成功、拒絕step_limit／無done／快照錯誤／count錯誤／fixture與Python3.8 syntax。

同一步後車讀到前車新記憶、原heuristic comments及跨episode可共用的庫語義維持。此隔離試跑只有一個episode，不宣稱驗證跨episode持久化或交通效果。四車每步5次LLM呼叫；寫入發生env.step前，失敗時早先寫入不回滾，保留診斷，不自動重試。

## 本地結果

Windows Python3.13.13、PYTHONDONTWRITEBYTECODE=1、stdlib／替身，無模型或sim載入、無套件安裝。check_memory_episode 3、check_memory_live_step 3、check_live_session 13，共19項通過、三條命令exit0。負面案例包含subtests；未在Windows執行shell或真episode，Spark仍待手動驗收。

## 手動執行

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
ss -ltn 'sport = :18080 or sport = :18082'
# 確認乾淨qwen-local且兩port均無listener後執行一次
bash validation/accept_memory_episode.sh
```

步數300是驗證上限，不改環境duration50秒／policy5Hz。實際終止仍以原環境done為準，時間上限由既有BudgetTransport／管理器執行。上限觸發／錯誤均非完整回合PASS，先保留原檔審查，不重跑。

## 回傳檔案：保留這些層級即可

```text
M22-R3-memory-episode-XXXXXX/
  git-commit.txt
  memory-config.json
  acceptance.json                   # 失敗時可能沒有
  console.txt
  memory.txt
  disk.txt
  service/service-console.txt
  live/<manager-id>/
    result.json                     # manager結果，務必保留
    server-console.txt
    traffic-console.txt
    traffic/<episode-id>/
      result.json                   # episode結果，同名但不同檔
      review.md
      step-0000.json
      step-0001.json
      ...                           # 全部step-*.json
```

不需傳test-chroma、模型、cache／暫存。可整理成獨立資料夾保留上述選定檔案；manager結果及episode結果勿互相覆蓋。最終acceptance會列出manager_report、episode_report及全部step_reports完整路徑。分析需同時看done、碰撞、到達與終止條件，不能把episode_terminal當成成功到達。
