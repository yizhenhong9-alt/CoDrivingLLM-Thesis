# M15：縮短 vLLM RPC socket 路徑

日期：2026-11-23。

## 修改前：Spark M14 真實失敗

使用者提供的 [result.json](../../../runs/M14-project-entry/20261123T084407Z-0ea03d24/result.json) 與 [server-console.txt](../../../runs/M14-project-entry/20261123T084407Z-0ea03d24/server-console.txt) 已於本地讀取。執行 commit 為 58d34739d6e49767ad8f448be3b59bc76ea341e8。

根因是 vLLM／ZeroMQ 建立 Unix socket 時，完整檔案路徑達 **108 bytes**，超過日誌明確指出的 **107 bytes** 上限。全為 ASCII，所以本例字元數也為 108。原工具將 VLLM_RPC_BASE_PATH 放在結果目錄下，M14 的結果目錄名稱較長，再加上 vLLM 產生的 36 字元 UUID，就超出限制。先前目錄較短的成功不能保證更長目錄也能啟動。

```text
/home/nclab/Yizhen/runs/M14-project-entry/20261123T084407Z-0ea03d24/rpc/9d3ffaaa-591a-4726-89ae-49622d865002
```

結果中的 error 為 Server exited before readiness，沒有 traffic_command／traffic_exit_code；正式主入口尚未被執行，也沒有取得模型回答，無法計算這次 parser 成功率。不是已觀察到的模型記憶體不足、parser 錯誤或正式主程式失敗。

停服紀錄為 exit_code=1、remaining_known_processes=[]、port_closed=true、warnings=[]。現有 clean_observation 要求退出碼 0，所以顯示 needs_shutdown_review；此標籤不能解讀為發現殘留程序。以上都是該次快照，不代表當下程序狀態。

## 修改內容

[run_qwen_live_session.py](../../validation/run_qwen_live_session.py) 將 RPC 暫存單獨放在 `/home/nclab/Yizhen/.rpc/<12位隨機ID>`，保留其餘快取與結果在每次執行目錄。

- 加上 vLLM UUID 後，Spark 標準路徑為 73 bytes，不隨結果目錄名稱增長。
- 建立前檢查 UTF-8 bytes 長度，不只計算字元數；超過 107 就在啟動模型前報錯。
- RPC 目錄限定個人目錄，解析並檢查基底路徑；每次建立獨立目錄，若名稱衝突即失敗，不沿用其他次執行的 socket。
- 環境變數只傳給這次啟動的程序，不改全域設定。不刪除舊結果／socket，也不更動模型、權重、啟動資源參數、parser、prompt 或安全政策。
- 實際 RPC 路徑仍記錄在 result.json 的 launch.environment_overrides.VLLM_RPC_BASE_PATH。

本次未更改 needs_shutdown_review 的既有判定，以免將啟動異常誤標為成功。

## 本地測試結果

[check_rpc_path.py](../../validation/check_rpc_path.py) 6 項通過，重現真實 M14 長路徑遭拒、短路徑通過、UTF-8 長度、獨立個人目錄、過長時不建立目錄，以及長結果目錄不再影響 RPC。check_live_session 13 項回歸通過，見 [test-results.txt](./test-results.txt)。check_project_entry 11 項也通過，共 30 項。

第一輪本地測試有 3 個錯誤：Windows sandbox 自身的暫存根目錄很長，正確觸發新長度檢查。測試改在工作區父目錄下建立並自動清理專屬短暫存目錄後通過；未放寬正式長度限制。測試不載入 vLLM／模型、不建立真實 Linux socket。仍需 Spark 實測。

## Spark 下一步

同步本修正後，維持原 M14 正式入口三步驗收目的，輸出至新的 M15 結果目錄以保留失敗證據：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git status --short
git pull --ff-only origin qwen-local
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/run_qwen_live_session.py --project-entry --parser strict --seed 0 --max-steps 3 --wall-seconds 600 --output-dir /home/nclab/Yizhen/runs/M15-project-entry
```

git status 若有未提交變更，先處理，不覆蓋。工具仍重查當下資源與埠，不依歷史 available 值決定。只回傳結果目錄中的 result.json、server-console.txt、traffic-console.txt，以及 traffic 子目錄中的 JSON／Markdown；不下載 socket 或 cache。正常完成後再核對實際步數、原始回答、parser 統計及停服結果。

## Spark 修改後實測：20261123T085404Z-498455d8

本地已讀取使用者回傳的 [外層 result.json](../../../runs/M15-project-entry/20261123T085404Z-498455d8/result.json)、[正式入口 result.json](../../../runs/M15-project-entry/20261123T085404Z-498455d8/traffic/20261123T085613Z-6577207b/result.json)、三份 step JSON 及兩份 console。這是使用者在 Spark 執行的證據，不是本地載入模型。

- commit=475192eb78de702d903e008c3c7cebcc47fd0b5a；正式入口 git_status 為空。
- traffic_command 確實指向 Run_multi_CAV_LLM.py --backend qwen；actual_environment_steps=3，三份 step 記錄各為 1、2、3；每步 3 個 physics ticks／0.2 秒，合計 0.6 秒。
- negotiation 3/3、action 12/12 通過 strict parser，15 次均 finish_reason=stop，無 no_text。逐筆原文、車號、解析值及環境動作已對照；此為本次樣本 100%，不是跨場景保證或決策正確率。
- 三步協商皆為 4 先於 3、5 先於 3。車號順序固定為 3、4、5、6：

| step_id | 模型 action 原文的 decision | 提交與環境動作 ID |
|---|---|---|
| 0 | SLOWER、FASTER、IDLE、FASTER | 4、3、1、3 |
| 1 | IDLE、FASTER、IDLE、FASTER | 1、3、1、3 |
| 2 | IDLE、FASTER、IDLE、FASTER | 1、3、1、3 |

每次請求都有獨立 API 紀錄，未重放舊動作。後兩步車 3 的 available_actions 只有 IDLE／FASTER，實際選到 IDLE。車 3 最終速度依序約 3.51、2.47、1.73 m/s；IDLE 在原控制器代表保留既有目標速度，並不保證瞬時車速維持，不能僅因持續減速就判定 parser 錯誤。本次未改其控制器或重新定義動作。

三步 done 都為 false，四台 CAV 各步 crashed=false；memory_module_imported=false。safety_guarantee=false 如原設定，不宣稱安全 supervisor 已介入；車 4、6 仍有步後約 6.49 m/s 的原速度行為。本次證明接線與短程運行，不能推論完整回合安全。

實際 RPC 路徑為 `/home/nclab/Yizhen/.rpc/f3ca20d9e54f`，73 bytes 的完整 socket 路徑配置可啟動。shutdown exit_code=0、埠關閉、已知程序無殘留、clean_observation=true；console 搜尋未見 EngineDeadError／semaphore／force killing／ZMQError。其他啟動警告仍可能存在，不宣稱零警告。

修改前在 ready 前因 108 bytes 路徑退出；修改後服務就緒並從正式入口跑完三步，這是短 RPC 路徑修正的實際幫助。

### Console 與停止原因

`project_step_limit_reached` 是到達設定的三步上限後正常停止，不是 error，也不是完整一回合結束。畫面 `apply-step=False` 屬舊單步旗標訊息；--project-entry 使用自己的步進迴圈，不依此旗標控制。此次應以正式入口及三份 step JSON 的真實步數為準。本輪只補結果文件，沒有更改已驗證程式。

### 下一步：一回合觀察

本次 config 為 duration=50、policy_frequency=5、simulation_frequency=15。可將程式上限提高到 300 步、wall-seconds=3600，讓原環境有機會先回報 terminal；仍只有一回合，done 即停止，無重試。環境本身含到達、碰撞與時間終止條件，所以 terminal 也不等於成功到達；完整回合是否完成及 parser 表現需等新結果才能判斷。
