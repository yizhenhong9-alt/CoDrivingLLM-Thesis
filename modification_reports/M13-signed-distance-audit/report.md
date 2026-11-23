# M13：負距離來源審查（不改公式）

日期：2026-11-23。

## 問題與原始證據

M10 真實車 3 提示出現前車位於前方 -6.59 meters。這段文字由程式生成，不是 Qwen 自己算出來的。

原 [getLaneInvolvedCar.inference](../../llm_controller/prompt_llm.py) 使用：

```
d = 其他車位置到「自車目的地」的直線距離 - 自車位置到目的地的直線距離
```

d<0 用來選前車，d>0 用來選後車。原程式再將負值直接寫入「in front ... meters」文字。因此負號有原有的分類用途；不能在分類前將所有 d 取絕對值，否則會破壞前後車判斷。

## 本地重現

[audit_prompt_distance.py](../../validation/audit_prompt_distance.py) 擷取原 method body 執行，僅移除註冊 decorator；用 stdlib sqrt 替代 NumPy sqrt，不改運算或分支。

自車位置取自已提供 snapshot，前車位置取自 prompt 顯示的四捨五入座標。自車路線末段 il1->o1 的終點依原 _make_road 與 destination property 重建為 (-111,-2)，不是原 JSON 直接記錄的 destination 欄位。

| 數值 | 公尺 |
|---|---:|
| 自車到自車目的地 | 122.68288 |
| 前車到自車目的地 | 116.09263 |
| 原差值 d | -6.59025 |
| abs(d) | 6.59025 |
| 兩車中心直線距離 | 21.15357 |

原 function 成功選出前車，並重現 -6.59 meters。來源檔 SHA256、輸入精度與數值見 [reproduction.json](./reproduction.json)。這是本地數值/原 method 重現，不是重新跑 Spark 模擬。

## 結論

如果只問為何顯示負號：因為原程式直接顯示帶符號的距離差。但修法不能簡化為「加 abs 就正確」：6.59 仍然不是這兩台車的實際中心間距 21.15。

此案例兩車在同一直線車道，中心距可直接由位置算得；21.15 不是前後保險桿淨距，也不能泛化成所有彎道路徑距離。未來應先固定提示中 distance 要表示哪種量，再改顯示與測試；若牽涉安全工具公式須另案審查。

本輪不修改 prompt_llm.py、不改任何安全公式、前後車分類、優先權或速度設定。沒有「修改後安全改善」可宣稱；這份報告是定位與重現證據。
