# M10：真實 Qwen 回覆驗證與主程序停服

日期：2026-11-23。

## 修改前證據

[M09](../M09-live-preflight/report.md) 已取得 Spark 真實資源與已安裝 source，以及 Step8J-R1 的原始設定與結果。前次短 API 回覆成功但正常停服未驗證；原程式同時終止群組可能讓 API/EngineCore 清理互相干擾，這只是候選原因，不能宣稱唯一根因。

舊 served-model-name 是 Qwen3-30B-A3B-Instruct-2507-FP8，新 client 的 model 是 Qwen/Qwen3-30B-A3B-Instruct-2507-FP8。若照抄舊設定，新 client 的 model preflight 會拒絕；必須先統一 API 別名。

## 修改範圍與保留項目

新增 [run_qwen_live_session.py](../../validation/run_qwen_live_session.py)，由使用者手動在 Spark 執行。這是會啟動真實模型的入口，不是離線測試。

保留原成功設定：既有本地 30B FP8 目錄、Python -I -B、同一 API 模組、127.0.0.1:18080、max-model-len=2048、單序列、batched tokens=256、eager、Triton MoE、KV=536870912、gpu-memory-utilization=0.40、safetensors、原 GPU UUID。無重新下載、轉換格式或權重逐檔檢查。

差異：served-model-name 統一完整名稱；明確 --shutdown-timeout=30；只向本次 Popen 建立的 API 主程序送一次 SIGTERM，不使用 killpg/pkill/killall/SIGKILL。新啟動程序仍使用獨立 session，僅利於追蹤，不向群組發訊號。所有快取、環境配置、RPC、暫存與 console 皆在本次 /home/nclab/Yizhen/runs 子目錄，不改全域 Shell/環境。

## 執行流程

1. 核對執行環境與 vLLM 版本、已安裝 --shutdown-timeout 選項，重讀當下 MemAvailable、GPU UUID 與 18080 監聽狀態。
2. 啟動門檻使用 max(64 GiB, 總記憶體*0.40)。64 GiB 是本輪保守操作門檻，不是已量測的最低需求；不保留資源，也不保證不 OOM。埠已占用或資源不足就不啟動，不停別人的程序。
3. 保存啟動設定、wrapper SHA256、Git commit 與 PID；最多等待 1200 秒啟動，每 30 秒顯示進度。不執行 1+1 或 R4/8F。
4. 確認 18080 的 listener 屬於這次程序家族，且 /v1/models 回傳完整名稱。
5. 呼叫既有 3.8 模擬 interpreter，執行 M05 live strict、seed 0；不含 --apply-step。不重試、不補備援動作。預期 1 次真實協商和 4 次 action；遇到較早失敗可能不足 5 次，保留原始回覆如實檢查。
6. 客戶端結束後，只向 API 主程序發 SIGTERM，外層最多等待 120 秒，再觀察已記錄子程序 10 秒。timeout=30 是 vLLM 內部請求等待設定，不是外層總程序退出保證。
7. 檢查主程序退出碼、已記錄 PID+start_ticks 是否消失、18080 是否關閉及 server console 關鍵警告；記錄前後 nvidia-smi 和 MemAvailable。

若仍有殘留、埠未關或偵測 EngineDeadError/semaphore/force killing，結果為 needs_shutdown_review，不強殺子程序。vLLM 自己的內部程式可能仍採取強制清理，需看 console；不能因 wrapper 沒 SIGKILL 就宣稱整體從未強制退出。

## 本地測試結果

[check_live_session.py](../../validation/check_live_session.py) 9 項通過，見 [test-results.txt](./test-results.txt)。使用 fake Popen/Mock，未啟動服務或發真實 signal。涵蓋模型別名、保留啟動參數、parent-only signal、已退出不送 signal、逾時不升級、client 禁止 apply-step、埠解析、PID 啟動時間識別與快取路徑/程序環境隔離。

尚未在 Spark 執行 M10；真實回答、停服、延遲與資源釋放結果不得預填。只測 helper，不能代替完整 subprocess/模型生命週期驗證。

## Spark 手動執行指令

確認工作樹乾淨，pull 本輪版本後執行：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/run_qwen_live_session.py --parser strict --seed 0 --output-dir /home/nclab/Yizhen/runs/M10-live
```

此指令會使用共用 GPU/RAM，載入已下載的指定模型。請保持終端機連線；進入停服階段後等待清理，不連按 Ctrl+C、不另外執行群組終止命令。若需中止，在正常執行階段單次 Ctrl+C 會進入 wrapper 的清理流程；任何強制關閉終端機的情況均不能保證 finally 完成。

回傳最終 result.json、server-console.txt、traffic-console.txt 與 traffic/*.json；失敗也全部保留，不直接重跑。只有 responses_validated 且 shutdown.clean_observation=true 才表示本次真實回覆流程通過且所列停服檢查未見異常。關鍵字檢查不是所有錯誤的完整偵測，仍需人工審查 console。

## 研究限制

只跑 seed 0 的 strict 提示，不是完整公平比較；legacy 真實回覆測試後續另排，不因兩版格式不同而宣稱誰較優。memory off 不代表模型 KV cache 關閉。安全公式、優先權與 5 m/s 限制未修改；無 env.step，因此不會產生交通通行/碰撞率證據。

2048/256 是本次候選測試設定，真實協商可能改變 action prompt 長度，若截斷或超出上下文就停止記錄，不能默認 M08 fixture 計數涵蓋一切。先審查真實回覆與正常停服，再規劃真正單步。
