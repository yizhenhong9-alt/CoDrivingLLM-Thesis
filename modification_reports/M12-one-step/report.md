# M12：明確啟用一次真實模擬步進

日期：2026-11-23。

## 修改前：已完成 M10 的真實回覆驗證

使用者提供 runs/M10-live/20261123T064746Z-45166eef 下的 result.json、server-console.txt、traffic-console.txt 和 traffic JSON。本地已讀取並核對：commit bcd6710；1 次 negotiation 與 4 次 action 的真實回答通過 strict 解析，動作為車 3 SLOWER(4)、車 4 FASTER(3)、車 5 IDLE(1)、車 6 FASTER(3)，環境步數為 0，memory_module_imported=false。

協商建議為 4 先於 3、5 先於 3。negotiation LLM 提供配對通行順序建議；各 CAV action LLM 分別參考協商、車道與安全資訊選動作。先行不是強制加速，讓行也不是程式強制覆寫 action。兩角色共用一個模型服務，並非兩份權重。

M10 實際 API usage：negotiation 輸入 452/輸出 26；四台 action 輸入 1014、835、949、813，輸出各 12。finish_reason 均為 stop。首協商約 30 秒、action 約 0.58–1.10 秒，只有單次且含初次請求因素，不能當正式效能基準。

停服紀錄顯示 parent-only、exit_code=0、已知程序無殘留、埠已關。完整 console 搜尋未見 EngineDeadError、semaphore 或 force-killing 字樣；日誌有 drain/30s 清理及 application shutdown complete。本次通過不等於長期可靠性已證明；其他啟動/效能警告仍存在，不宣稱零警告。

## 修改範圍

[run_qwen_live_session.py](../../validation/run_qwen_live_session.py) 加入明確 --apply-step，預設仍為 false。開啟時將選項傳給既有單步入口，驗證真正步數為 1；否則仍要求 0。成功狀態分為 single_step_validated 與 responses_validated，wrapper 不預填執行步數。

[qwen_step.py](../../llm_controller/qwen_step.py) 在既有單一 env.step 呼叫前保存逐車 action ID，呼叫後保存 physics ticks、模擬時間與 env.new_action。若既有 safety_supervisor 有改動動作，可由 submitted_vehicle_actions 與 step_observation.environment_action 區分；不關閉或改寫其政策。

CLI 原本就保存 initial/final vehicle 狀態及 actual_environment_steps，保留以檢查位置、速度、碰撞與完成原因。原本提示前截速至 5 m/s、優先權、安全公式維持；這不代表所有 physics tick 都有額外強制 5 m/s 上限。

## 本地測試結果

更新後 live-session helper 13 項、single-step flow 14 項，合計 27 項通過，見 [test-results.txt](./test-results.txt)。新增明確 --apply-step 的命令測試、逐車提交紀錄、physics ticks 換算與環境動作分開記錄檢查。皆為 fake process/environment，不載入模型，不代表真實道路運動已驗證。

## Spark 執行方式（本次已完成）

更新本輪版本並確認工作樹乾淨，再執行：

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/qwen-vllm034-py312/bin/python validation/run_qwen_live_session.py --parser strict --seed 0 --apply-step --output-dir /home/nclab/Yizhen/runs/M12-one-step
```

會啟動指定 30B FP8，共用 GPU/RAM；程式先重查當下資源與埠，不以歷史 92.49 GiB 保證。使用原啟動/主程序停服流程，不重做已通過的合成或離線測試。

重新建立 seed 0 初始場景並重新問模型，不重放舊 JSON 動作；即使 seed 相同也不保證 LLM 回答完全相同。全部回覆驗證成功後才 env.step 一次，不跑完整回合、不自動重試或以 IDLE 補錯。

回傳 result.json、server-console.txt、traffic-console.txt、traffic/*.json。預期 wrapper=single_step_validated、traffic=single_step_complete、actual_environment_steps=1，並核對 shutdown.clean_observation、逐車對應與最終狀態。若碰撞、terminal 或動作被既有 supervisor 更改，照實記錄；完整一次 step 不等於決策安全。

## 未修改事項

負距離與衝突敘述保留原基線，另見 [M13 審查](../M13-signed-distance-audit/report.md)。本次不將 negotiation 建議變為硬性控制、不修改 action 優先權、不改公式、不啟用 memory on。

## Spark 實測結果：20261123T072921Z-61956b0a

本地讀取使用者提供的 [result.json](../../../runs/M12-one-step/20261123T072921Z-61956b0a/result.json)、[traffic JSON](../../../runs/M12-one-step/20261123T072921Z-61956b0a/traffic/20261123T073128Z-053d29a8.json) 與 console 紀錄。這是使用者在 Spark 執行後回傳的證據，並非本地載入模型。執行版本為 d5bc64f404dede217e54d0a172462c19109cb1f9。

- wrapper 為 single_step_validated；traffic 為 single_step_complete，actual_environment_steps=1。
- 一次 negotiation、四次 action；通行建議為車 4、5 各先於車 3。逐車提交為 3:SLOWER(4)、4:FASTER(3)、5:IDLE(1)、6:FASTER(3)，與環境記錄動作一致。
- 前進 3 個 physics ticks，共 0.2 秒。四台 CAV 的 crashed 均為 false；done=false、reward=0。這只證明單步串接完成，不能推論完整回合安全或決策品質改善。
- 車 3 速度由 5 降至約 3.51 m/s；車 4、6 由 5 升至約 6.49 m/s；車 5 維持 5 m/s。原程式只在提示前截速，沒有在所有模擬更新中強制最高 5 m/s；本次未改限速，後續需另行確認研究設定。
- memory_module_imported=false。停服 exit_code=0、埠已關、已知子程序無殘留，clean_observation=true；這不代表所有啟動警告皆消失或長期可靠性已證明。

相較 M10 的零步驗證，M12 的實際幫助是確認解析後動作能按正確車號送入環境並產生狀態變化；兩次單一場景結果不能作為 parser 或駕駛品質的比較實驗。

## LLM 角色與提示修改說明

原始 agent 檔案保留；Qwen 專用組裝位於 [qwen_step.py](../../llm_controller/qwen_step.py)。negotiation 仍扮演 traffic police officer，提出通行順序建議；各 CAV action LLM 仍扮演 driving assistant，參考建議與場景選動作。兩個邏輯角色使用同一 Qwen 服務，各次請求分別組裝提示。

實際修改包括：action 的 ChatGPT/OpenAI 身分改為一般 driving assistant；重新整理提示段落；memory off 時移除空白 memory 提示段；strict 模式改用明確 JSON、數字車號與可用動作清單。原交通規則與注意事項仍引用原方法，協商建議未改為強制動作。因此這是保留角色分工的 Qwen 適配，並非逐字相同的原版 prompt；未來比較模型效果時需控制 prompt/parser 等變因。
