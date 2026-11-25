# M20-R3：原格式欄位對照與真 Chroma 驗收準備

日期：2026-11-25。狀態：本地替身通過，Spark 完整 Chroma 安裝及真持久化測試待使用者手動執行。HNSW 已由 R1-09 證據確認來源建置與基本人工向量查詢通過；不重做該步。未進入 M21。

## 變更與保留方法

- M20-R3-01：從 R2 原方法重播中凍結兩筆 [fixtures.json](../R2-memory-semantics/fixtures.json)：M16 step 0 車 3 的危險尾段、step 35 車 3 的空資訊。包含原 query、page_content、四個 metadata 欄位及原記憶呈現文字。它們是離線測試資料，非真實命中結果、不作正式訓練記憶。
- M20-R3-02：[check_chroma_memory.py](../../../validation/check_chroma_memory.py) 加入原四欄／原文往返測試，確認 JSON metadata 封裝沒有改值。真 Chroma 開關測試改用這兩筆文字＋人工向量，再從全新 Python 子程序讀回核對，避免同程序快取冒充持久化證據。
- M20-R3-03：[run_chroma_acceptance.sh](../../../validation/run_chroma_acceptance.sh) 提供手動 Spark 腳本：核對第三個環境、相依 dry-run、安裝完整 Chroma、pip check、14 項真／替身測試與完整 console。只使用該個人環境與個人 runs，不載入 embedding／Qwen，無模型下載或交通模擬。

不修改原作者 repo、不恢復其註解、不啟用 Qwen memory on；query 最後兩行與 page_content 最後一行、原 None／動作陣列字串／規則評語保留為對照。來源只以額外 source 欄加入測試 metadata。未採用步後寫入或固定快照提案，正式寫入時機仍未接線。M17 prompt、安全公式／門檻／優先權／速度處理未改。

## 本地驗證

既有 Python 3.13.13，PYTHONDONTWRITEBYTECODE=1；未安裝套件或載入模型。

| 測試 | 結果 |
|---|---|
| check_chroma_memory.py | 14 項：13 通過、1 略過；真 Chroma 只由 Spark --real-chroma 啟用 |
| check_local_memory.py | 16 項：15 通過、1 略過；Windows 無 symlink 權限 |
| check_memory_off.py | 5/5 通過 |
| check_vehicle_actions.py | 13/13 通過 |

合計 46 通過、2 略過。詳細 console 與 source SHA256 保存於本目錄。新增持久化子程序測試在本地未執行，不宣稱通過。Bash 腳本目前只作靜態審查，需在 Spark 執行驗證。

## Spark 操作與預期

先同步此次 Git 更新至 qwen-local（更新前檢查分支與工作樹，不覆蓋修改），然後手動執行：

```bash
bash /home/nclab/Yizhen/src/CoDrivingLLM-Thesis/validation/run_chroma_acceptance.sh
```

腳本預期既有 memory-chroma0415-py312 已有 numpy 1.26.4 與成功編譯的 chroma-hnswlib 0.7.3。對整套 Chroma 使用 --no-build，禁止新的來源編譯；已安裝的 hnswlib 保留。若 uv 在該設定下仍拒絕 hnswlib，保留錯誤再調整解析方法，不卸載或重編、不自動移除限制。

暫定約束：chromadb==0.4.15、numpy==1.26.4、chroma-hnswlib==0.7.3、pydantic<2、posthog<4；保留已用的固定建置工具。解析成功不等於 API／ABI 可用；pip check 與真 Chroma 測試需依序成功。最後應為 14 項測試 OK 與 M20-R3 Chroma acceptance: PASS。若任何一步失敗，set -e／pipefail 停止並列出結果目錄，不改系統套件或其他環境。

此步只用 CPU 和少量人工資料，不需要啟動模型、檢查 GPU 埠或重跑交通 seeds。CPU／RAM 仍共用，但不作大量平行編譯；腳本不發起新的來源建置。所需模型權重及真 MiniLM 英文檢索仍是後續工作。

## 後續順序

1. 真 Chroma 持久化／重開成功後，固定實際套件清單。
2. 準備 MiniLM 固定 revision 與來源／hash 驗證，再測真向量與原模板情境的相關性。
3. 確認 metadata 與 prompt 呈現的對照，再進 M21。若修正 None、動作呈現或空資訊篩選，須單獨列出方法差異，不視為單純本地 embedding 替換。
