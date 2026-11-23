# M06：Spark 離線驗證與 Git 同步準備

日期：2026-11-23。

## 修改前

M01–M05 分散在多個測試入口，M05 尚未通過實際 Spark Python 3.8 模擬器驗證。本地完整 fixture 試跑因缺少 gym 停止。

## 修改內容

新增 [validate_spark_offline.py](../../validation/validate_spark_offline.py)，依序執行 37 項 M01–M05 測試，再執行 strict/legacy 兩次真實模擬器 fixture，檢查步數為 0、未匯入 memory、沒有模型呼叫。失敗立即停止並保存 console/result.json。

子程序使用當次指定 interpreter；不 pip install、不更新環境、不啟動模型。快取、matplotlib 設定與暫存導向輸出子目錄；設定只影響本次子程序，不改全域 Shell。子程序隱藏 CUDA 裝置、BLAS/OpenMP 執行緒設為 1、圖形採無視窗模式。這些不是硬體資源隔離，也不能保證其他函式庫完全不寫其他位置。

## 共用資源影響

離線測試仍使用共享 CPU、RAM、磁碟 I/O 與磁碟空間，不代表專屬資源。此程式不載入模型，不主動建立 CUDA 計算，不要求停止其他程序，不改 Docker、驅動或系統套件。未做 GPU 系統追蹤，不能把程式審查當成硬體實測。

之後 live 接 Qwen 時，服務會使用共用 GPU/統一記憶體；需重新盤點當下 available，歷史 92 GiB 不作保證。現有虛擬環境檔案以讀取為主，但 Python 套件仍可能有初始化副作用；若遇到非個人路徑寫入錯誤，先回報，不擴大權限。

## 本地與遠端結果

本地已可執行 37 項測試；M06 runner 的完整流程因本地缺 gym，預期在 fixture 階段停止。實際本輪驗證結果另記於 [本地驗證輸出](../M06-local-validation/)。這不是 Spark 通過紀錄。

Spark 結果尚未取得；後續將提供固定 commit 與手動同步指令，不假設遠端工作樹乾淨。

後續補記：已取得使用者提供的 20261123T034727Z-a0ccb710 結果。Spark Python 3.8 的前四組 37 項通過；strict fixture 在記錄來源路徑時失敗，legacy 未執行。修正與後續狀態見 [M07](../M07-relative-source-path/report.md)，原始失敗紀錄保留。
