# M03：車號與多車動作檢查

日期：2026-11-23。

## 修改前證據

原入口依回傳順序攤平動作；原 MultiAgentAction.act 使用 zip。兩車但只有一個動作時，zip 只產生一組，沒有數量完整性保證。此行為由離線案例重現，不代表過往模擬已實際漏車。

原車輛顯示標籤為 id(self)%1000；reset 另賦予 vehicle.id。新版沿用後者，驗證唯一性，不更改原物件或顯示標籤。

## 修改範圍

新增 [vehicle_actions.py](../../llm_controller/vehicle_actions.py)。EpisodeVehicleMap 在 reset 後保存該回合 simulation ID 與物件；ActionBatch 保存本步受控車順序及可用動作，以 caller 記錄的 episode/step/expected vehicle 檢查回覆。回覆順序打亂仍按原受控車順序產生整數 tuple；漏車、重複、過期、錯車或車輛物件變更均拒絕。曾收到錯誤回覆的 batch 不可 finalize，不自行補 IDLE。

## 修改後驗證

[check_vehicle_actions.py](../../validation/check_vehicle_actions.py) 的 BatchTests 涵蓋亂序、缺車、重複、陌生車號、錯車回覆、跨步/回合、換物件、換順序及禁止自動備援。結果見 [test-results.txt](../test-results.txt)。

## 幫助與限制

Windows Python 3.13.13：BatchTests 的 10 項測試通過，包含原版 zip 截短重現與新版缺車拒絕案例。

離線測試可確認資料未齊全時不產生可提交的 tuple。尚未接入 env.step，所以不能宣稱正式模擬已有此保護。回合 ID 必須由呼叫端唯一產生；動態新增車輛的登記與車號生命週期仍需正式整合處理。尚未驗證 Spark Python 3.8、真實 Qwen、各場景閉環；安全政策與 5 m/s 限制未修改。
