# M23-R5：off／on版本與舊式車名碰撞的獨立核對

2026-11-26，使用者要求仔細審查是否memory修改關鍵程式造成新失敗。本項只做本地Git與原檔審查，未改控制器、名稱函式、guard、安全處理或跑任何sim／Qwen。

## 直接核對

[audit_label_history.py](./audit_label_history.py) 以Git blob比較off commit21799bdc2abc3b85d1c8562e90827e8287eeaf3d與實際恢復執行commit add6a861bebebe122fd684ed8578e093d8593103；七個相關檔案逐byte相同：highway_env/vehicle/kinematics.py、envs/common/abstract.py、envs/intersection_env.py、llm_agent_action.py、llm_agent_negotiation_system.py、prompt_llm.py、vehicle_actions.py。對應blob SHA256與證據統計見 [label-history-audit.json](./label-history-audit.json)。不是僅憑目前checkout推斷歷史版本。

名稱唯一性guard在兩版本都存在，Git -S追溯為65a4d99（M01–M06接線）加入，早於off20seeds；不是M22／M23新增。但必須區分：Vehicle.__str__命名是原作者程式，guard是我們較早Qwen接線加入的防混淆檢查，不應把guard稱為原作者原始功能。

M18 seed1全部107步的已保存vehicle_identifiers皆唯一。相同seed1四車初始state（id／位置／速度／crashed）對off與第一次on，以及off與恢復後on，皆完全相同，最大位置差0、速度差0。此證據只涵蓋紀錄的四台CAV，不等於已核對全部HDV或整個場景內部狀態。

off初始車3 label為MDPVehicle #640、第一次on為MDPVehicle #520；同樣的初始交通state並沒有固定相同的舊式label。第一次on7台road車label互異並完成第0步，恢復後on卻在第0步guard前停止。這次calls=[]、step=0、queries=0、writes=0，396筆snapshot未變，與HTTP400無關。

## 原因層級

Vehicle.__str__使用class name與id(self)%1000。Python物件識別值本身在物件存活期間唯一，但取餘數後不再保證唯一；兩台同class車的餘數可相同。這不是simulation vehicle.id重複，也不是物理碰撞；label衝突有可能涉及背景HDV。

reset設定NumPy與random seeds來固定交通隨機數，不控制Python程序的記憶體配置、id(self)或取餘數。未觀測到off撞名只代表那些執行通過guard，不能保證未來off也不撞名；既有20seeds未必具有與另一程序相同的label。

memory-on的確改了qwen_episode入口：在gym匯入／env建構前額外建立OriginalMemorySession、HTTPclient、讀取設定與進行status；qwen_step在名稱檢查前也額外有memory模式驗證與import。這些會增加Python物件配置，**有可能間接改變車輛物件的配置識別值**。目前沒有受控allocation實驗或完整撞名清單，不能證明是哪個配置造成本次衝突；也不能說memory完全不可能影響。已證明的是命名／安全／交通reset程式未改，以及名稱設計本來不具跨程序穩定唯一性。

直接根因是guard看見重複字串名稱；根本脆弱點是舊式名稱依賴物件識別尾碼。為何恰好本次配置撞名仍未完整觀測。已不支持「新增guard」、「改壞TTCP／安全公式」、「seed1交通初始四車變了」的說法。

## 不應採取的處理與下一步

不可刪guard／任意換seed／重試直到不撞名而挑成功一次。也不可只修改names映射，原helper多處以str(vehicle)字串反查，須整條名稱鏈一致。若改成穩定唯一名稱，會影響prompt文字，須另編號、測試及說明與舊off的可比性；本審查尚未實施此改動。

最小診斷改進是先保存所有simulation_id／legacy_label與重複分組，再保留原guard拒絕；它不應改寫車輛名稱或決策。接著才能規劃一致命名修正與隔離驗收。現有缺失的重複清單不能靠本地位置推回。

本地以Windows Python3.13.13／stdlib執行離線audit PASS，沒有模型、模擬器、SSH或新實驗。使用者／其他工作留下的R4報告刪除狀態原樣保留，本項另寫R5，不還原或提交該刪除。
