# M22-R2：真正 Qwen＋原版 memory on 單步聯測

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
