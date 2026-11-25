# M22-R3：單一seed完整memory-on回合整合驗證

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
