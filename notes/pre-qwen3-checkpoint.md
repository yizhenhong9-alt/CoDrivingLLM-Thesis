# 本次聊天總結的截止點：CoDrivingLLM 接入 Qwen3 之前

日期：2026-11-20。後續總結必須明確區分服務部署與交通程式模型替換。

- 遠端由使用者手動操作實驗室 Windows RDP；目前工具所在本機不是 RDP。
- 官方 Qwen3-30B-A3B-Instruct-2507-FP8 已在個人 WSL 成功提供 API，
  Windows 到 API 的短回答及停止資源釋放已驗證；單卡 4090，新增大型資料在 E:/YiZhen。
- CoDrivingLLM 的 negotiation/action 尚未接入 Qwen3；原模組仍指定 gpt-4o-mini。
- 本地與 RDP 透過個人 GitHub 的 qwen-local 分支同步；作者來源保留為 upstream。
- 驗證程式集中 validation/；固定 IDLE 的單 step、相同 seed 重跑及 5 steps 已通過。
- pandas 1.3.5 下 append/concat 的五個人工案例及 48 次實際觀測比較通過。
  依使用者選擇，正式觀測採公開 append，保留套件版本與測試紀錄。
- 離線 prompt 擷取使用程序內 SDK 替身，不呼叫模型、不建立 DrivingMemory、不執行 env.step。
  最近一次已擷取 negotiation，因原加速安全工具必填 env 與呼叫端不一致而中止。
- 經函式本體與作者歷史檢查，env 未被使用；使用者同意刪除這個參數，
  撤回先前補傳 env 的方案，保留安全公式。最新修正仍需 RDP 回歸測試及擷取重測。
- 生產入口的 memory off/on CLI、本地 embedding、Qwen3 專用模組、輸出契約驗證、
  真實 prompt token/延遲測試及 Qwen 閉迴路實驗尚未完成。

以上為當前狀態備註，不是逐字聊天匯出。後續測試結果應另行更新，不得把待測項目視為已完成。
