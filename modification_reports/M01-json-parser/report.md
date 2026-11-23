# M01：JSON 回覆解析

日期：2026-11-23。執行位置：Windows 本地，Python 3.13.13。

## 修改範圍

新增 [output_schema.py](../../llm_controller/output_schema.py)，原版 [action agent](../../llm_controller/llm_agent_action.py) 未修改。新版要求完整 JSON、精確動作名稱、正確車號與完整協商配對；異常回覆回報錯誤，不猜測備援動作。M02 後場景必須明確傳入。

## 修改前結果

直接擷取原版兩個 method body 執行，未載入模型或模擬器。9 項重現測試符合觀察：NOT IDLE 被判為 IDLE，IDLE or FASTER 被判為 FASTER，缺 decision 欄位的 comment 仍可被接受為 FASTER。相同協商 JSON 改縮排、空白或欄位順序後被解析為空清單。原格式及簡單合法 JSON IDLE 則可成功。

證據：[重現程式](../../validation/reproduce_original_parsers.py)、[原始結果](../../validation/original_parser_reproduction.json)。這些是人工案例，不是 GPT 或 Qwen 的實際錯誤率。

## 修改後測試

[新版測試](../../validation/check_output_schema.py) 7 項已通過，涵蓋合法編號、錯車號、模糊動作、未知動作、重複欄位、配對漏項與 JSON 排版差異。測試案例與兩版輸出格式不同，不能視為真實模型的同一回覆 A/B 比較。

## 幫助與限制

已證實新版在指定人工案例能拒絕誤判輸入、讀取合法 JSON 排版變化。尚未證實真實 Qwen 解析率、通行率、碰撞率或延遲改善。尚未接入 agent；未驗證 Spark Python 3.8。後續保留同一原始回覆交給兩版 parser 的紀錄，prompt 不同的比較另列。
