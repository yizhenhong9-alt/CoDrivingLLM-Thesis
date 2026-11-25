# M21-R4：即時唯讀檢索 session 與完整 prompt 計數

## Spark 成功回傳與原檔審查（M21-R4-07）

使用者 console：`M21-R4 online readonly memory: PASS; queries=4; LLM fixture calls=5; env.step=0`、exit0；結果目錄 `/home/nclab/Yizhen/runs/M21-R4-online-memory-x0pF7u`。
已實際審閱本地 [回傳資料](../../../../runs/m21-r4/) 四份檔案（acceptance、config、commit、capture），使用 [audit_returned.py](./audit_returned.py) 重核對，exit0。詳細結果與證據SHA256見 [spark-audit.json](./spark-audit.json)。

- 完整commit：7a786a914a9c7f1a9e772cdc6b71bd708deb2cba，根目錄與capture一致。
- memory環境tokenizer對照舊R2兩份messages計數為1129／949，與已驗收Qwen環境相同；本地審查未重新載tokenizer。
- 目前情境四次query均由原scenario最後兩行還原且hash相符；車3／6為空資訊、top1=fixture-1；車4／5為原危險尾段、top1=fixture-0。原文、原四欄與額外test_only source逐筆相符，注入順序等於實際候選順序。
- 4/4均兩筆候選、兩筆注入、零排除；注入段去除後base prompt hash一致。negotiation沒有記憶段。
- negotiation輸入453 tokens；車3／4／5／6為1092／987／1101／928，加預留256後最大1357，低於2048。session token_checks=9，即四次prepare計數＋五次完整請求檢查，並非九次LLM呼叫。
- 重新以strict parser解析5份fixture原文，與保存結果一致；negotiation的legacy比較被拒絕是預期比較結果，不是strict驗收失敗。四台fixture action皆IDLE，不能解讀成Qwen實際選擇。
- status=validated_not_applied、mode=fixture、sent_to_model全部false、actual_environment_steps=0，沒有提交動作。legacy cloud memory_module_imported=false。
- session opened=true／closed=true／queries=4／final_snapshot_verified=true；config hash與回傳設定一致，snapshot維持 `24d3717e8019cf575195ffd321945a1d964423444ffe24cb2b2e25a3234c7546`。

本節取代以下建立時「Spark待驗」狀態，證據足夠，不需補檔或重跑R4。沒有回傳服務console或DB，未獨立逐檔盤點服務停服；session closed指client scope關閉，不能混稱整個服務程序關閉的直接證據。此關只支持目前兩筆測試庫上的即時唯讀檢索／完整計數接線，沒有Qwen生成、交通結果、全面相關性或M22寫入證據。

下一關可把已驗證的即時session與真negotiation／CAV Qwen回答在同一零步進流程串起，再接M22原版逐車步前寫入。正式主入口仍off，不將本次凍結唯讀驗收當作完整原版memory-on等價。

2026-11-25。設定、scope 生命週期、memory HTTP 完整 token 計數與目前情境驗收腳本已實作；本地替身通過，Spark 待使用者手動執行。正式應用預設 off／factory on 拒絕均不變，未實作 M22 寫入，不允許 memory 模式 env.step。

## M21-R3 究竟驗了什麼

R2 已經真實檢索並保存兩份帶記憶 prompt。R3 核對這些檔案與原 M16 hash、重算完整 token，再啟動原已部署 Qwen，送兩次 action 請求，strict parser 核對合法車號／可用動作，最後停止自己的服務。Spark 回覆 SLOWER／FASTER、API 輸入1129／949與 tokenizer 一致、0步進、正常停服，已審查通過。

R3 沒有重新檢索、沒有目前模擬情境、沒有 env.step 或 memory 更新；它確認「凍結的兩份真檢索 prompt 能得到合法真回答」。不能從動作與 off 相同推論 memory 有效／無效。此次 R4 才在目前情境內每台 CAV 即時查詢，先以 fixture 回答驗證 CPU 接線，避免為此再次啟動 GPU。

## 基線與編號

開始時 qwen-local／dc5d6ff，工作樹乾淨。沒有改原作者副本、已完成 seed 結果、M17 文字、安全公式／門檻／優先權／signed distance／速度處理；沒有安裝新套件、重新部署 Qwen 或 Windows 載入模型。

| 編號 | 變更 |
|---|---|
| M21-R4-01 | [memory_session.py](../../../llm_controller/memory_session.py)：明確 JSON 設定、scope 開啟／關閉、唯讀／固定 schema／預期 snapshot／tokenizer 身分 guard，關閉後拒絕使用，保留原始失敗與 close 診斷 |
| M21-R4-02 | [memory_http.py](../../../llm_controller/memory_http.py)／[serve_local_memory.py](../../../validation/serve_local_memory.py)：同一 memory 服務新增 /count；回傳完整 messages hash、token count 與指定 Qwen tokenizer model／revision，無第二個 HTTP 服務 |
| M21-R4-03 | [qwen_step.py](../../../llm_controller/qwen_step.py)：session 橫跨 negotiation＋各 CAV，negotiation 只計數、不注入；action 即時 retrieve／完整預算檢查。維持零步進 gate；live 零步進只接受 active OnlineMemorySession，不能用任意 adapter 偷開步進 |
| M21-R4-04 | [run_qwen_single_step.py](../../../validation/run_qwen_single_step.py)：明確 --memory-config，限 strict／max_tokens256／無 apply-step；未提供仍完全 off。fixture 原封鎖全部網路；有設定時只開放指定 127.0.0.1 memory port，其他主機／Qwen API／IPv6 仍拒絕 |
| M21-R4-05 | [accept_online_memory.py](../../../validation/accept_online_memory.py)／[手動腳本](../../../validation/accept_online_memory.sh)：新隔離庫、現有 sim 目前情境四次真檢索與完整計數，LLM fixtures、0步進；[程序 helper](../../../validation/memory_service_session.py) 增加顯式 tokenizer 選項 |
| M21-R4-06 | [check_online_memory.py](../../../validation/check_online_memory.py)、回歸 console、測試摘要及本報告 |

## 設定與生命週期

設定固定 format=m21-r4-readonly-v1、原 query manifest、memory port／timeout、預期 corpus snapshot、context2048／output256。沒有 host 參數或 cloud fallback。caller 進 scope 時檢查服務唯讀、同一 snapshot 與指定 Qwen tokenizer；同一 client／session 供多台 CAV 共用，scope 結束核對 snapshot 再關 client。不關閉外部服務或資料庫，服務程序由驗收 parent 管理，只停止自己子程序。

session 是可供回合共用的生命週期介面，**此次實際接入的是零步進驗收 scope，不是 Run_multi_CAV_LLM 正式 episode CLI 已完成**。run_episode 與主入口仍 off。完整 episode 的 integration 及 M22 逐車步前更新尚待接線。固定 snapshot 是明確唯讀驗收模式，不是把原作者邊檢索邊寫的語義改成凍結庫後宣稱等價。

## 同一服務即時計數

memory 3.12 環境已有 Transformers5.22.2／tokenizers／Jinja2。只有明確 --qwen-tokenizer 才載既有 Qwen 本地 tokenizer，local_files_only、trust_remote_code=False、offline、載入時 socket block；不載 Qwen AutoModel 或權重，不安裝套件。MiniLM encoder 繼續 CPU，模型／tokenizer 分別為獨立 closure，不互相覆寫。

每個完整 system messages 經同一服務 apply_chat_template(add_generation_prompt=True)＋encode(add_special_tokens=False)。client 核對 messages SHA256、有限正整數 token count、指定 model／revision。metadata 不作摘要，原四欄與 query 保持；超預算仍整筆移除2→1→0，零筆還超限就停止。negotiation 原文不變，但也納入完整 token 檢查。off 不發 /count／retrieve／status。

這不是從「model／revision 字串」獨立驗證 tokenizer 檔案來源；沿用先前已核對本地 Qwen 目錄，並在 Spark 重新拿 R2 已核對兩份 messages 作交叉檢查，要求 memory 環境計數恰為1129／949。memory 環境尚未實測載此 tokenizer，所以本地通過不能代替 Spark；若缺相依或不相容就保存錯誤，不自行補裝或改版。

原 memory /embed 服務不變；R7 /status 額外提供 tokenizer identity（未啟用則 null），既有 /add／retrieve／protocol／manifest 格式不改。/count 仍受1MiB request／response限制，不記錄全文。loopback 沒有身分認證；同主機／帳號的程序仍可呼叫。snapshot 全庫讀取只在這個小型測試使用，未承諾大庫效能。

## Spark 驗收內容

1. 在本次獨立 run 建新 schema 測試庫，寫兩筆原模板，source=test_only；不碰既有 R2 DB 或正式資料。
2. 停止自己 create 子程序，重開 readonly＋tokenizer，對照已審查 R2 messages 確認1129／949；不啟 Qwen GPU。
3. 現有 sim 3.8 建立原 intersection 情境、明確 seed0、0步進；fixture negotiation／action只測格式不是安全政策。四台 CAV 各按目前 scenario 即時 retrieve k2、計數與組 prompt；不像 R3 重播保存的整份 prompt。
4. 要求五次 fixture call（1 negotiation＋4 action）、四次 query、全部 strict parsed、每份 input＋256≤2048、注入文字去除後 base prompt hash一致、session opened／closed／final snapshot verified。父程序最後再核對 corpus未改。

這不是重跑已完成的 seed0 回合或20 seeds，而是初始化情境、不步進的接線驗收。沒有真 Qwen 回答、無交通結果，不宣稱目前情境下 memory 有效。通過後才接實際逐步流程／M22，不用小型通過替代正式比較。

## 本地測試

Windows 既有 Python3.13.13、stdlib／替身、PYTHONDONTWRITEBYTECODE=1；無真 ML／tokenizer／sim載入、無雲端／Spark／SSH／GPU。66項通過、0略過：online9、HTTP12、prompt9、retrieval6、single-step14、off5、entry11，七個命令exit0。新增檢查涵蓋 /count hash／identity、未啟用 counter拒絕、scope一次開關、每次完整請求計數、關閉後拒絕、corpus變動／唯讀檢查、例外仍關閉且保留原錯誤、fixture只能連指定memory port、超限在送LLM前停止、memory步進拒絕、3.8 AST／無ML匯入。

測試 console、命令摘要與 source SHA256 見 [test-results.json](./test-results.json)。編輯器七個本次主要Python檔無錯誤。PowerShell對native stderr空行部分包裝為System.Management.Automation.RemoteException，非Python traceback，原逐項結果與exit0均保存。Bash／Spark實際MiniLM與Qwen tokenizer共存及sim capture仍待手動證據。

## Spark 手動命令

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis status --short --branch
# 確認 qwen-local 且無修改後：
git -c safe.directory=/home/nclab/Yizhen/src/CoDrivingLLM-Thesis pull --ff-only origin qwen-local
free -h
df -h /home/nclab/Yizhen
ss -ltn 'sport = :18082'
# 確認沒有 listener 後：
bash validation/accept_online_memory.sh
```

有listener就停止本次操作，不處理他人程序。腳本只啟動CPU memory服務＋本地tokenizer，不啟GPU Qwen，新增cache／tmp／DB／結果全在 `/home/nclab/Yizhen/runs/M21-R4-online-memory-*`。子程序只SIGINT自己的memory服務，等待30秒；未退出保留PID與錯誤，不強殺或刪鎖。

預期最後 `M21-R4 online readonly memory: PASS; queries=4; LLM fixture calls=5; env.step=0`、exit0。請回傳完整console、根目錄git-commit.txt／memory-config.json／acceptance.json、capture/<id>.json。若失敗再回傳readonly/service-console.txt與capture-console.txt；不要下載DB／cache，不自行補裝套件或重跑到成功。
