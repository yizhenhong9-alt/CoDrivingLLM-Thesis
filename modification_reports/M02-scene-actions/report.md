# M02：場景動作設定

日期：2026-11-23。

## 修改前

M01 新版 parser 僅支援 intersection 三種動作，無法直接解析 highway 換道。這是新增工具的限制，非原作者所有場景皆有錯。原 action agent 的既有設定為 intersection/merge 使用 1、3、4，highway 額外使用 0、2。

## 修改範圍

新增 [action_config.py](../../llm_controller/action_config.py)，將場景設定與共用 JSON 解析分開。parse_action 必須明確傳入 scene。保留 intersection/merge 的 IDLE=1、FASTER=3、SLOWER=4；highway 額外 LANE_LEFT=0、LANE_RIGHT=2。這是依既有 agent 的設定，不表示已驗證 merge/highway 真實環境。未知場景拒絕執行。

## 修改後驗證

使用 [check_vehicle_actions.py](../../validation/check_vehicle_actions.py) 的 SceneTests：檢查各場景編號、路口禁止換道、未知場景與設定副本隔離。結果與本輪完整測試輸出記錄於 [test-results.txt](../test-results.txt)。

## 幫助與未驗證

Windows Python 3.13.13：SceneTests 的 3 項測試通過。M01 的 7 項 parser 測試同步重跑通過。這是本地離線結果，不是完整場景模擬結果。

parser 不再寫死單一場景，可以明確切換並保留編號。各場景實際可用動作仍須由環境提供，不由模型決定。未修正既有 Discrete(3) 宣告，未改優先權、安全公式或速度限制，未接入正式 agent。
