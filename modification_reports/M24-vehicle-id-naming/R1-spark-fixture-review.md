# M24-R1 Spark 完整命名／prompt／token 驗收

2026-11-26。使用者回傳 `C:/master's thesis/runs/M24-launch-Leljkk`，原壓縮檔保留，解包在其 extracted 子目錄。Spark結果目錄 `/home/nclab/Yizhen/runs/M24-vehicle-id-6iSfFe`。執行commit為9fefc893ea85c492e39114a8c97365f9dbf373e7，回傳 git-status.txt 為空。

## 實際結果

seed0、seed1皆 `validated_not_applied`、`M24-simulation-id`、memory off，environment_steps與actual_environment_steps皆0。每seed五筆call紀錄全部sent_to_model=false：一筆協商與四筆CAV動作prompt，回覆由fixture提供，不是真Qwen推論。

兩seed各七台road車輛，名稱唯一且後綴與simulation_id一致：

| 本次角色 | 模擬類別 | ID |
|---|---|---|
| HDV背景車 | IDMVehicle | 0、1、2 |
| CAV受控車 | MDPVehicle | 3、4、5、6 |

受控車身份以initial_vehicles的id與四筆action context.vehicle_id交叉核對，不能只靠號碼大小猜角色。此編號為episode內身份，不是跨seed同一實車的永久編號，也不是影像辨識。新的車3、車6可以分別表示，不再由Python位址取餘數產生同名。

token報告status=measured，all_fit=true；兩seed合計10份完整message含chat template的計數全通過2048 context限制。最大input1017，預留output256，合計1273，剩775。token報告保留fixture SHA256供核對。

## 失敗的是最後打包

console最後為 `tar: .：檔案在讀取時已變更`，腳本exit1。原腳本將review.tar.gz寫入正在封裝的diag目錄，即使排除檔名，建立檔案仍可能改變目錄mtime，觸發GNU tar檢查。修正為輸出到同層 `${diag}-review.tar.gz`，位於輸入目錄以外。不是命名guard、安全helper、Qwen或token budget失敗。使用者外層整理出的壓縮檔已包含兩fixture、token報告、console與git資訊，能完成本次審查；無須重跑這兩個fixture來補打包。

## 能支持與尚不能支持的結論

已支持：Spark真環境reset後，seed0/1初始road中CAV／HDV均取得一致唯一文字編號；原prompt／解析接線可完成零步fixture流程；這10份off prompt可容納於context。

尚未驗證：真Qwen是否理解新編號並做出有效決策、實際步進後整episode的身份與行為、memory-on檢索與token預算、碰撞率或到達率改善。不得稱為完整交通實驗成功，也不得說Qwen已辨識CAV／HDV。此結果不改變新命名off/on配對基線的必要性評估，未啟動正式批次。
