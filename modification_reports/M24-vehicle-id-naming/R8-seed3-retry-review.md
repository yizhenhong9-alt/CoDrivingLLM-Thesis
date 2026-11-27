# M24-R8：seed3第二次漏答與重試前段memory檢索差異

2026-11-27。使用者回傳 `C:/master's thesis/runs/M24-review-4n5ban44.tar.gz`，原檔保留，解包至同層M24-review-4n5ban44。Spark retry run：`/home/nclab/Yizhen/runs/M24-intersection-memory-on-20seeds-seed3-retry-3OlRsh`。實際commit5700bae3bc5b7e860ea05403257886089c007c93。

## 已核對結果

296個匯出檔SHA256全部通過。prior-attempt的260個固定來源檔hash通過R7來源contract，再執行R6原始資料鏈稽核。恢復收據ready、原庫860未變、copy physical hash核對通過、排除60個ID完全吻合、restored_count800與seed2 snapshot精確一致，prompt_changed=false／strict_changed=false。

重試16個完成步驟與第17個失敗決策紀錄完整：81次Qwen call（80份已解析、1份缺項拒絕），64次query／64筆verified writes，800→864；逐筆檢索來源、四欄metadata、write receipt與rolling snapshot核對通過。完成步驟車名與ID一致，無CAV碰撞；不代表episode成功到達。失敗step16只1個negotiation call，0 action／0 query／0 write／0 env.step。

memory session closed=true、final_snapshot_verified=true。Qwen shutdown exit0、port closed、known processes空、warnings空、clean observation=true。retry-result狀態stopped_requires_review，attempt2；沒有啟動seed4。原860庫與retry864庫都保留，沒有下一次重試。

最終864筆snapshot：`8f856c7273b54a953a104c056c366167e5a67e01d6c1ba10739ff89e42d324b6`。

## 與第一次失敗對照

| | 第一次step15 | retry step15 | retry step16 |
|---|---|---|---|
| Pairs | [[3,2],[4,3]] | 同左 | 同左 |
| 回覆 | 只有3先、4後 | 3先2後；4先3後 | 只有3先、4後 |
| strict | Missing conflict decisions | 通過 | Missing conflict decisions |
| input tokens | 490 | 488 | 487 |
| output tokens | 16 | 26 | 16 |
| finish_reason | stop | stop | stop |

兩次失敗raw response都與固定JSON示例逐字相同；支持範例誘導假說，未證明模型內部根因。不是輸出額度截斷，也不是guard憑空增加一組衝突。strict要求的缺項確實存在；不改成靜默略過。

### 不能把相同Pairs當成完全相同prompt

三份完整messages SHA256不同；車速／位置／距離已改變。逐步比較發現兩次step0初始受控state相同，step2的action batch首次不同，step3起initial_vehicles及negotiation prompt開始不同，negotiation raw response首次不同是step15。因此不能用step15一敗一成證明相同輸入下模型隨機翻轉。

step2車2的action差異有直接prompt證據：原次注入兩句 `[1] / might not safe, you should be careful and check`，retry改為兩句 `[3] / recommended to FASTER`。原次Qwen選SLOWER，retry選FASTER；車3–5的memory句也有差異但當步仍選FASTER。這是觀測到的輸入與輸出分歧，不是已證明單一因果效果。

## 額外發現：檢索差異不是只有相同分數的tie

step2車2的query兩次逐字相同，都是equal close／delta speed0.0摘要；兩次corpus_count皆808，但snapshot不同（各attempt的新episode ID／metadata及後續寫入不同，不能只憑筆數稱語料完全相同）。

- 原次命中兩筆seed1的完全相同equal-close摘要，distance0、score1，action `[1]`、comments為careful/check。
- retry命中兩筆該次step1的Conflict info is empty，distance約0.805627、score約0.194373，action `[3]`、comments為recommended FASTER。

這是明顯的候選／相似度差異，不可僅以「等分ID排序」解釋。原seed1的兩筆ID屬800個保留紀錄，不在刪除60筆清單。本地沒有DB／query embedding向量，尚未證明差異來自刪除後索引、embedding輸出、Chroma候選搜尋或其他因素；不能直接斷言HNSW損壞，也不能說800 logical snapshot一致就保證後續每個query一致。

現有action template沒有相似度cutoff，按原語義接納top2；本輪沒有擅加cutoff、過濾空摘要或改安全公式。協商階段本身仍未注入memory，因此上面的檢索差異可經前面action／物理軌跡間接改變後續場景，不能說失敗協商直接讀了錯誤memory。

## 後續範圍

一次方向1重試已使用完畢，不再重跑挑成功，不自動進seed4。保留原860、副本864與兩個attempt全部資料。

下一步適合分兩項隔離驗收：(1)凍結兩份失敗協商prompt與相鄰成功prompt，測試候選提示修改是否完整回答所有pair，仍保持strict；(2)對原／恢復後語料的獨立副本做同query檢索對照，釐清上述score1與0.194差異。前者若改正式prompt就是新版本，不能無說明接成同版本20seed；後者不能操作原庫或以Windows載入模型。兩項本輪都尚未啟動，也沒有修改正式prompt／檢索策略或部署新服務。

完整messages hash、64筆新ID、296檔hash、回覆與最早分歧見 [R8-seed3-retry-audit.json](./R8-seed3-retry-audit.json)。本輪只以Windows stdlib讀JSON與收據，不開Chroma、不載模型、不SSH、不操作共用帳號他人資源。原作者副本與R4既存刪除維持不動。
