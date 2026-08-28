# Phase 2D Crash-Before-Terminal Analysis

## 範圍與證據邊界

- 分析日期：`2026-08-26`（`Asia/Taipei`）。
- Artifact：`notes/artifacts/phase2d/full_episode_memory_off.json`。
- SHA-256：`83C1A91102761159CCA9E26B88572BDD9337C3CE10F386E2BAF12F396B79462D`。
- Run：一個 `intersection-multi-agent-v0` episode；Ollama `qwen2.5:7b`；endpoint `http://127.0.0.1:11435`；Memory OFF。
- 執行時 repository HEAD：`60cc9a3f4bd9f865aab3964e9b8c6d706b688e0a`；本次檢視 HEAD：`03efa382f976e7b4ce191ba1b7edc293491eaa55`。
- 本次僅進行 post-run 唯讀分析，未重跑 episode、未啟用 Memory、未修改 source code。
- `MDPVehicle #832` 等識別字來自執行時的 `id(...) % 1000`，只在這份 artifact 對應的 process 中有意義。

Artifact 保存了每個 policy step 前後的 controlled-vehicle positions、centralized conflict records 中的 speeds、raw/parsed LLM outputs、actions、reward 與 per-CAV crash flags；未保存 headings、每個 simulation substep 的 state、collision partner ID、完整 background-vehicle trajectories，以及各車 post-step speed。因此無法精確重建碰撞的每一幀。

## 最後十個 policy steps：Confirmed evidence

`A>B` 表示 centralized negotiation 選擇 A 為 `first_vehicle`、B 為 `second_vehicle`。Action 格式為 `semantic_action/action_id`。Steps 33–42 的所有 conflict records 都記錄相關車輛約為 `6.488 m/s`；這是 centralized negotiation 在 distributed processing 前取得的 speed。

| Step | Step 前 positions（`#832`; `#296`; `#360`; `#312`） | Centralized negotiation | Decisions（`#832`, `#296`, `#360`, `#312`） | 結果 |
|---:|---|---|---|---|
| 33 | `(2.000,15.509)`; `(-6.188,2.000)`; `(-2.030,-12.826)`; `(9.974,-2.063)` | `296>832`; `832>360`; `296>360`; `312>832` | `IDLE/1`, `IDLE/1`, `IDLE/1`, `FASTER/3` | reward `0`; no crash |
| 34 | `(2.000,14.402)`; `(-5.081,2.000)`; `(-2.065,-11.720)`; `(8.897,-2.319)` | `296>832`; `832>360`; `296>360`; `832>312` | all `IDLE/1` | reward `0`; no crash |
| 35 | `(2.000,13.295)`; `(-3.974,2.000)`; `(-2.020,-10.614)`; `(7.857,-2.696)` | `296>832`; `832>360`; `360>296`; `312>832` | `IDLE/1`, `FASTER/3`, `IDLE/1`, `FASTER/3` | reward `0`; no crash |
| 36 | `(2.000,12.188)`; `(-2.867,2.000)`; `(-1.893,-9.515)`; `(6.867,-3.191)` | `296>832`; `832>360`; `296>360`; `832>312` | `IDLE/1`, `FASTER/3`, `FASTER/3`, `IDLE/1` | reward `0`; no crash |
| 37 | `(2.000,11.081)`; `(-1.760,2.000)`; `(-1.682,-8.428)`; `(5.942,-3.799)` | `296>832`; `832>360`; `296>360`; `832>312` | `FASTER/3`, `IDLE/1`, `IDLE/1`, `IDLE/1` | reward `0`; no crash |
| 38 | `(2.000,9.974)`; `(-0.653,2.000)`; `(-1.387,-7.361)`; `(5.096,-4.513)` | `296>832`; `832>360`; `296>360`; `312>832` | `IDLE/1`, `FASTER/3`, `IDLE/1`, `IDLE/1` | reward `0`; no crash |
| 39 | `(2.000,8.867)`; `(0.454,2.000)`; `(-1.007,-6.322)`; `(4.343,-5.323)` | `296>832`; `832>360`; `296>360`; `312>832` | all `IDLE/1` | reward `0`; no crash |
| 40 | `(2.000,7.760)`; `(1.561,2.000)`; `(-0.544,-5.316)`; `(3.694,-6.220)` | `360>832`; `296>360`; `312>832` | all `IDLE/1` | reward `0`; no crash |
| 41 | `(2.000,6.653)`; `(2.668,2.000)`; `(0.000,-4.352)`; `(3.161,-7.190)` | `832>360`; `296>360` | `FASTER/3`, `IDLE/1`, `IDLE/1`, `IDLE/1` | reward `0`; no crash |
| 42 | `(2.000,5.546)`; `(3.775,2.000)`; `(0.622,-3.437)`; `(2.752,-8.218)` | `832>360`; `296>360` | `FASTER/3`, `IDLE/1`, `FASTER/3`, `IDLE/1` | reward `-2.5`; terminal; crash `[True, True, False, False]` |

Terminal step 後的位置為 `#832=(2.000,4.843)`、`#296=(4.479,2.000)`、`#360=(1.060,-2.886)`、`#312=(2.565,-8.897)`。Info 為 `speed=6.049`、`cav_crashed=True`、`cost=1.0`、`agents_dones=[True, True, False, False]`。

## 1. Centralized negotiation 與 conflict 演變

### Confirmed evidence

- 原始 regex parser 成功解析最後十步的所有 centralized results，沒有 negotiation parser failure。
- `#296–#832` conflict 持續存在到 step 39，且每次皆建議 `#296` first、`#832` second。
- Step 39 中，`#296` 與 `#832` 距各自 route conflict point 分別約 `0.548 m` 與 `5.883 m`。
- 從 step 40 起，`#296–#832` pair 同時從 centralized conflict input/output 消失，因此兩車的 distributed negotiation text 也不再包含彼此。
- `is_conflict()` 要求兩車仍被 destination-distance comparison 判定在 sampled route conflict point 之前；任一車被判定已越過該點，pair 即回傳 `False`，即使兩個 physical rectangles 仍可能靠近。
- Steps 41–42 只協調 `#832>#360` 與 `#296>#360`，對最後 crash 的兩車已沒有直接 passing constraint。

### Likely explanation

- `#296` 很可能在 step 39 左右越過 sampled route conflict point，使 `#296–#832` 在兩車物理車身完全離開交會區前就退出 negotiation set。
- 因而可能形成 temporal/geometric blind window：route-point logic 認為 conflict 已結束，但 rectangular collision geometry 仍可能在稍後重疊。

### Cannot determine from artifact

- Artifact 未保存 exact conflict-point coordinates，無法確定 predicate 改變的精確時刻。
- 無法單憑此 artifact 判定這是 intended approximation、paper/repository simplification 或 defect。

## 2. Negotiation 建議與 final decisions 的一致性

Passing-first 並非直接 action command，所以 first vehicle 選擇 `IDLE` 不必然矛盾；但 prompt 明確指出，被建議 passes second 時「better to slow down」。

### Confirmed evidence

- Step 35：`#296` 對 `#360` 應 second，卻選擇 `FASTER`。
- Step 36：`#360` 對 `#832`、`#296` 均應 second，卻選擇 `FASTER`。
- Step 37：`#832` 對 `#296` 應 second，卻選擇 `FASTER`。
- Step 42：`#360` 對 `#832`、`#296` 均應 second，卻選擇 `FASTER`。
- Step 42 的 `#832=FASTER` 與其相對 `#360` 的 first 建議一致；`#296=IDLE` 不直接違反 first 建議，但也沒有積極保證先通過。
- Step 42 已不存在 `#832–#296` negotiation result，無法用當步 passing advice 評估兩車彼此的 action。

### Likely explanation

- Centralized ordering 只是 natural-language advisory context，controller 不會強制執行；distributed model 可以輸出格式正確但違反建議的 action。
- Passing order 會逐步重新決定且可能反轉：`#832>#360`（step 39）、`#360>#832`（step 40）、再回到 `#832>#360`（steps 41–42）。系統沒有持續性的 right-of-way commitment。

## 3. Parser 正常但 decision semantics 不合理

### Confirmed evidence

- Step 33 `#832` 有三項 negotiated conflicts，prompt 明示 `acceleration will cause serious danger, must decelerate`，raw explanation 卻聲稱沒有 conflict；最終為 `IDLE` 而非 `SLOWER`。
- Step 35 `#296` 收到相同的 serious-danger warning，卻選擇 `FASTER` 並宣稱 acceleration safe。
- Step 36 `#360` 對兩車皆應 second，收到 `must decelerate`，卻選擇 `FASTER`。
- Step 37 `#832` 應讓 `#296` 先行且收到 `must decelerate`，卻選擇 `FASTER`。
- Step 42 `#360` 對兩車皆應 second 且收到 `must decelerate`，仍選擇 `FASTER` 並聲稱沒有 immediate danger。
- Steps 41–42 的 `#832` raw explanation 聲稱沒有 conflict，但 negotiation text 明確仍有 `#360`。其 safety summary 同時顯示 `Conflict info is empty`，因為該 helper 只計算 ego 被建議 passes second 的 pair，而 `#832` 對 `#360` 是 first。

因此 parser success 只證明 output-format compatibility，不代表 safety reasoning、negotiation adherence 或 decision rationality 正確。

### Likely explanation

- `qwen2.5:7b` 似乎過度重視「no vehicles in the current lane」等 generic phrase，而忽略 cross-route conflict 與 passing-order instruction。
- Prompt 自己也可能對仍有 conflict、但被建議 first 的車輸出 `Conflict info is empty`，增加模型誤認「no conflict」的可能性；這是獨立於 parser 的 information-semantics gap。

## 4. 最可能 crash chain

### Confirmed evidence

1. `#296` 與 `#832` 以相同的 recorded conflict speed（約 `6.488 m/s`）接近共同 crossing。
2. 到 step 39 為止，negotiation 一直要求 `#296` first、`#832` second。
3. 最後十步中兩車都未選過 `SLOWER`；`#296` 在 steps 35、36、38 選 `FASTER`，`#832` 在 steps 37、41、42 選 `FASTER`。
4. Pair 在 step 40 從 conflict detection 消失，也移除了 mutual passing advice 與 TTCP safety treatment。
5. Step 42 為 `#832=FASTER`、`#296=IDLE`；step 後兩車 crash flags 為 true，而 `#360`、`#312` 為 false。
6. Simulator 在每個 substep 以 rotated rectangles 執行 collision check；任一 controlled vehicle crash 即觸發 terminal。

### Most likely explanation

最可能的鏈條是：`#296` 通過 sampled route conflict point，而 `#832` 沒有用 `SLOWER` 明確讓行；conflict detector 隨後移除 `#296–#832`；兩車在 retained speed targets 下繼續移動；`#832` 不再收到關於 `#296` 的 warning，並於 steps 41–42 選擇 `FASTER`；兩車 physical rectangles 在 step 42 的 simulator substep 中重疊，因此兩者同時標記 crashed。

`#360` 在 step 42 違反 negotiation 選擇 `FASTER` 是 confirmed inconsistency，但不太可能是 direct terminal collision，因為 `#360.crashed=False`。Artifact 無法排除其對整體 geometry 的間接影響。

### Cannot determine from artifact

- 未記錄 collision partner。同步 crash flags 與 positions 強烈支持 `#832–#296` collision，但不能完全排除兩車分別撞到未完整記錄的 background vehicles。
- 無法重建 exact time-to-collision、headings、rectangle overlap、acceleration profiles，以及首次設定 `crashed=True` 的 simulator subframe。
- 未做 controlled replay，因此不能宣稱「某一個 `SLOWER` 必然可避免 crash」。

## 5. `action_space.contains()` discrepancy

### Confirmed evidence

- Declared per-agent space 是 `Discrete(3)`，Gym nominally 只接受 `0,1,2`。
- Executable longitudinal map 是 `{4:'SLOWER', 1:'IDLE', 3:'FASTER'}`；`MultiAgentAction.act()` 直接以此 map dispatch。
- Episode 全部 43 個 joint actions 都通過 executable-map validation 並實際執行。最後十步中，含 ID `3` 的 actions 皆使 `action_space.contains()==False`；all-IDLE actions 為 true。
- Executable path 未發生 remap、clip、reject 或 exception，ID `3` 確實呼叫 `FASTER`。

### Conclusion

對本 episode 而言，這是 declaration mismatch，沒有在 dispatch 後改變 vehicle behavior，也不是此次 collision 的直接原因。不過其他依賴 Gym validation、sampling 或 wrapper 的 workflow 仍可能受影響，所以它依然是 implementation/interface discrepancy。

## 6. Simulator/controller/reward discrepancies

### Confirmed controller facts

- 原始 per-CAV loop 在每次 distributed prompt 前，會把 intersection 中大於 `5 m/s` 的 `ego_veh.speed` 直接指定為 `5`；full-episode runner 忠實沿用此行為。
- Centralized negotiation 在這四次 speed assignment 之前發生，因此 conflict records 顯示 `6.488 m/s`，distributed processing 隨後才直接改變 speed。
- `MDPVehicle.FASTER` 改變 discrete target-speed index；`IDLE` 不會把 `target_speed` 重設為當前速度，只是不再下新的 high-level speed change。因此 `IDLE` 可能保留先前的 `FASTER` target，並不保證 physical constant speed。
- `safety_guarantee=False`，沒有 supervisor 覆寫 unsafe LLM actions。
- Conflict safety helper 只評估 ego 被建議 passes second 的 relationships；被建議 first 的車可能在仍有 negotiated conflict 時收到 `acceleration is safe` / `Conflict info is empty`。

### Likely contribution

- Prompt 將 `IDLE` 描述為保持 current speed，但 retained target-speed dynamics 可能繼續先前的 acceleration objective。這對 steps 35、36、38 選過 `FASTER`、之後 steps 39–42 選 `IDLE` 的 `#296` 特別相關。
- 每輪直接 clamp physical speed、卻不等價地 reset target speed，形成非標準 controller transition，可能造成反覆 re-acceleration，也使 centralized speed snapshot 與後續 distributed-control state 不一致。
- Route-point predicate 在 physical clearance 前移除 conflict，很可能使 crash 前缺少 `#832–#296` warning。

上述是 repository implementation behaviors 與可能的 paper–code discrepancies；這個單一 artifact 不足以授權或支持修改。

### Confirmed reward discrepancy

- `_agent_reward()` 對所有 controlled vehicles 都使用 `self.vehicle.speed`（第一台 controlled vehicle）計算 speed term，而不是 parameter `vehicle.speed`。
- 每台 crashed controlled vehicle 的 collision reward 是 `-5`，四車 cooperative average 中兩車 crash 可解釋 observed `-2.5`（共同 speed term 為零時）。
- Reward 在 dynamics 後計算，影響的是 reward attribution，不會選擇 actions，也沒有造成 collision。

### Cannot determine from artifact

- 無法確認 speed clamp、retained target speed、conflict predicate 或 reward code 是否與 paper 實驗使用的未公開版本完全一致。
- Artifact 未記錄 individual target speeds 與 individual post-step speeds，無法量化每項因素的精確貢獻。

## 7. Implementation blocker 與 Memory ON readiness

### Implementation blocker

未發現阻止既有 pipeline 執行的 runtime implementation blocker：transport、兩個 parsers、action dispatch、simulator transition、terminal detection 與 artifact logging 都完整成功。此次 crash 是 simulator outcome，不是 Python process crash，也不能僅因 crash 就判定 code bug。

但後續解讀必須保留以下 research risks：

- format-correct 但 safety-inconsistent 的 LLM decisions；
- negotiation 只有 advisory effect，沒有 enforcement/persistence；
- route-point conflict predicate 可能在 physical clearance 前停止 warning；
- `IDLE`/target-speed semantics 與 prompt wording 不完全一致；
- 直接 5 m/s speed assignment 與 reward-speed attribution discrepancy；
- declared/executable action-space mismatch。

### Memory ON recommendation

技術上可以安全進入 **controlled Memory ON preflight/verification**，但不建議直接執行完整 Memory ON performance episode。下一階段應先用獨立、完整記錄的 database 驗證 retrieval timing/query、injected content、shot count、update timing/content、initial state 與 persistence。

Memory 不應被當成修補 unsafe action 的 fallback；比較時必須保持此次 Memory OFF trajectory 與上述 implementation discrepancies 不變。目前不能宣稱 Memory ON 能改善 collision rate。Matched Memory OFF/ON episode 或 repeated evaluation 仍需另行批准與可重現的 seed/provider-sampling protocol。
