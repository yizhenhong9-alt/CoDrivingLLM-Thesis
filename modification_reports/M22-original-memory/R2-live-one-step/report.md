# M22-R2：真正 Qwen＋原版 memory on 單步聯測

## 回傳審查（2026-11-25）

補件完成：使用者另提供本地 `runs/m22-r2/live/result.json`，已重跑離線審查為 PASS。manager commit、traffic 路徑與 memory session 對應 episode；既有模型revision、loopback18080、context2048、GPUutil0.40、KV536870912、Triton與shutdown30設定一致。shutdown exit_code=0、remaining_known_processes=[]、port_closed=true、warnings=[]、clean_observation=true，與正常停服console相符。此 warnings 是管理器的特定停服警告清單，不表示所有啟動warning皆不存在。先前「缺manager」段落是歷史狀態，現在已解除，無需補傳或重跑。

### 原版同一步記憶可見性

只讀核對原作者副本：`llm_agent_action.py:35` 逐車迴圈，`:45` 取得本車回答，`:46` 原有但註解的 memory_update 位於下一車之前；主入口 `Run_multi_CAV_LLM.py:77` 先取得全部車輛決策，`:85` 才 env.step。因此恢復原記憶呼叫後，較後車可能檢索同一步較早車的新紀錄。原提交的retrieval/update呼叫被註解，不能說原專案當時已實際運行此現象；可說原預留的更新位置具有這項語義。M22依已授權的原版順序恢復，沒有改成post-step或每步凍結庫。

這些紀錄是「當前情境＋選擇的動作＋既有heuristic評語」，並非已觀察到步後成效的歷史經驗。由此可能產生同一步資訊混入、車輛順序依賴；本次核對沒有證明它造成決策錯誤。若未來改成全部車回答後才寫入或step後附實際結果，須另立方法變更，不能宣稱與原版等價。

Spark console PASS／exit0；commit `8980e7eb5bcdbe8ec849a4ae8ec38033201d6ccc`，工作樹紀錄乾淨。已回傳 acceptance、config、commit、episode result／review／step 與三份 console。[離線審查](./audit_spark.py) 可得證據通過，數值與檔案SHA256見 [spark-audit.json](./spark-audit.json)。**尚缺 manager result.json，不將停服證據審查標成完整完成。**下文歷史待執行文字以此更新。

實際 Spark 層級（先前回傳清單未清楚標明兩個同名 result.json 的完整階層，現修正）：

```text
/home/nclab/Yizhen/runs/M22-R2-memory-live-step-Zk1p13/
  acceptance.json
  git-commit.txt
  memory-config.json
  console.txt
  service/service-console.txt
  live/20261125T092853Z-c72b7973/
    result.json                      # manager：本次尚未回傳
    server-console.txt
    traffic-console.txt
    traffic/20261125T093059Z-9faa2dc0/
      result.json                    # episode：已回傳
      review.md
      step-0000.json
```

使用者本地重整為 `runs/m22-r2/live/` 放兩份 console，`runs/m22-r2/traffic/20261125T093059Z-9faa2dc0/` 放 episode 檔；不要求回傳時保持原階層，審查依檔案內容與 acceptance 原路徑對照。

| 車輛 | 查詢前庫筆數 | 注入筆數 | 真正決策 | 步後速度 m/s |
|---|---:|---:|---|---:|
| 3 | 0 | 0 | SLOWER／4 | 3.511660 |
| 4 | 1 | 1 | FASTER／3 | 6.488340 |
| 5 | 2 | 2 | IDLE／1 | 5.000000 |
| 6 | 3 | 2 | FASTER／3 | 6.488340 |

- 一次 negotiation 回覆指定4先於3、5先於3，strict與四車action共5/5通過；legacy negotiation比較拒絕是舊parser格式差異，正式選用strict沒有失敗。
- 五次API真回覆均 finish_reason=stop、內容與raw一致；API prompt token與服務計數一致，分別453／1087／932／1064／922。最大1087＋256=1343≤2048，無記憶被排除。server console有五次chat POST 200。
- 四筆 verified 寫入、唯一ID、原四欄、source commit／scope／step／vehicle、文字與metadata hash、候選來自先前寫入、逐車snapshot鏈及最終snapshot均對應。查詢前庫筆數0／1／2／3，符合逐車步前更新。未另開Spark DB檢查。
- 原 comments仍為heuristic：車3為 might not safe…，空衝突為recommended to FASTER，車5即使選IDLE也保留此評語；沒有把本次實際步後結果回填。
- env.step確實一次，3 physics ticks、0.2模擬秒；動作[4,3,1,3]與提交一致。reward0、done=false、cav_crashed=false、cost0，四車crashed均false。停止原因是一步上限，不是完成episode或成功到達。該步無碰撞不能推論全程安全或memory改善。
- negotiation耗時30.651秒、四次action約1.194／0.575／1.062／0.574秒；這是API呼叫牆鐘時間，不能視為純memory延遲或多次統計。
- server console包含正常drain、engine manager stopped及Application shutdown complete，未見Traceback／EngineDeadError／force killing；仍有deprecated入口、eager設定、FlashInfer kernel、MoE設定、sampling defaults等啟動警告，不能宣稱完全沒有warning。這些字樣本身不能證明下載已發生；不因此變更既有Qwen環境。

需補傳且只需補傳：上述 `live/20261125T092853Z-c72b7973/result.json`。其 shutdown.exit_code／remaining_known_processes／port_closed／clean_observation 與啟動設定尚待獨立核對；不需重跑實驗。

2026-11-25：已完成驗收腳本與本地測試，Spark 尚未執行，沒有真 Qwen／模型／sim 在 Windows 載入。M22-R1 回傳審查通過後進入本階段，不代表正式 seeds 實驗開始。

## 編號與範圍

- M22-R2-01：[驗收器](../../../validation/accept_memory_live_step.py) 在既有 sim Python3.8 啟動單一 memory CPU 服務（含本地 tokenizer），建立全新空 test-chroma，config test_only=true；呼叫既有 Qwen 啟停管理器及正式專案入口，seed0、max-steps1、wall-seconds600、memory on。Qwen 環境、模型、啟動參數不變。
- M22-R2-02：[手動腳本](../../../validation/accept_memory_live_step.sh) 保存 commit、資源資訊、console，結果只放 `/home/nclab/Yizhen/runs/M22-R2-memory-live-step-*`。不讀寫先前庫，不自動重試、不重跑既有20 seeds。
- M22-R2-03：[離線 gate 測試](../../../validation/check_memory_live_step.py) 驗證成功 receipts，拒絕零步進、fixture、hash 損壞、未知候選、異常停服與錯誤庫筆數，並檢查 Python3.8 syntax。

預期四車查詢前筆數0／1／2／3，候選0／1／2／2；每車真正回答 strict 通過後依原方法寫入，再處理下一車；四車完成後呼叫一次 env.step。所有寫入保留原四欄與 heuristic comments，無 post-step 更新、成功篩選、凍結庫或額外實驗模式。未修改控制器、安全公式、門檻、優先權、signed distance、速度處理或預設 memory off。

驗收器核對真呼叫標記、strict parser、完整 prompt 預算、已完成較早寫入的候選文字／metadata、唯一ID、receipt hash、快照鏈、最終服務4筆，以及 Qwen exit0／port關閉／已知子程序清空／無警告。真正碰撞、reward、done 與動作存原 step 檔，不把格式正確或流程通過當成安全改善；terminal 可能包括碰撞，必須另審原檔。

## 本地測試

Windows Python3.13.13，PYTHONDONTWRITEBYTECODE=1，stdlib與既有替身，無新增套件。下列三條命令均 exit0，29項通過：

```text
python validation/check_memory_live_step.py   # 3 tests（含6個拒絕情境 subtests）
python validation/check_live_session.py       # 13 tests
python validation/check_original_memory.py   # 13 tests
```

CLI負面測試顯示 argparse error 是預期拒絕；非測試失敗。本地只驗證 gate 與既有接線，不能證明 Spark 實際聯測通過。shell 腳本本地未以 bash 執行。

## Spark 手動執行

先確認工作樹乾淨、18080及18082都沒有 listener，再執行一次：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
ss -ltn 'sport = :18080 or sport = :18082'
bash validation/accept_memory_live_step.sh
```

既有管理器啟動一個真正 Qwen 服務，沿用 parent-only 停服與觀察；外層不使用 timeout 強制中斷其清理流程。memory helper 只 SIGINT 自己的 child 並等30秒，未停止會報錯要求人工檢查，不強殺。失敗不自動重跑，先保留部分寫入與 raw replies。

請回傳根目錄 console、git-commit.txt、memory-config.json、acceptance.json，以及 acceptance 指向的 manager result.json、episode result.json、step-0000.json；同時回傳該次 server-console.txt、traffic-console.txt、service/service-console.txt 以審查啟停與錯誤。不要搬模型、cache或DB。沒有 acceptance.json 時仍保留其餘檔案供診斷。

單步通過僅代表完整接線可運作；尚非完整episode、跨step動態穩定性或正式seed研究結論。
