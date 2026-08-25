# Original CoDrivingLLM Paper–Code Analysis

> 階段：Analysis First（Original CoDrivingLLM Paper–Code Analysis）  
> 分析日期：2026-08-24（Asia/Taipei）  
> Repository：`https://github.com/FanGShiYuu/CoDrivingLLM.git`  
> 分析 baseline：`master`，HEAD `f9e71fe`（2025-09-25）  
> 論文：*Towards Interactive and Learnable Cooperative Driving Automation: a Large Language Model-Driven Decision-Making Framework*  
> 本文件只記錄分析結果；本階段未修改 source code、configuration、dependency 或 Conda environment，也未執行 experiment。

## 0. 分析範圍、證據與重要限定

- 已讀取 repository root `AGENTS.md`、repository tree、Git status/history、`README.md`、`requirements.txt`、頂層 entry point、`llm_controller/` 核心實作、`highway_env/` 的 environment/action/control/observation 路徑及論文全文。
- 本機 PDF 題名為 `paper/Towards Interactive and Learnable Cooperative Driving Automation - A Large Language Model-Driven Decision-Making Framework.pdf`。由於目前 Python 與 `codriving_yizhen` 都沒有 PDF parser，本次以同題 arXiv HTML v3 讀取全文並以本機 PDF 題名、作者與 DOI 交叉核對。arXiv v3 日期是 2025-09-19，repository README 引用正式 IEEE TVT DOI `10.1109/TVT.2025.3552922`；因此版本間的排版或少量文字差異仍應視為可能。
- Git status 在分析前為 `master...origin/master`，未追蹤項目已有 `AGENTS.md` 與 `paper/`。這些不是本次建立的 baseline source changes。
- Paper evidence： [arXiv HTML](https://arxiv.org/html/2409.12812)、[arXiv record](https://arxiv.org/abs/2409.12812)。Code evidence 均引用本 repository 的實際檔案與 symbol。
- 本文件的 `Match Level` 只採用：`Fully implemented`、`Partially implemented`、`Simplified`、`Hard-coded`、`Not found`、`Unclear`。

## 1. Repository architecture

### 1.1 Entry point 與頂層結構

| 區域 | 實際角色 | 主要證據 |
|---|---|---|
| `Run_multi_CAV_LLM.py` | 唯一公開執行腳本；建立 Gym environment，逐 policy step 建立 memory/negotiation/action objects，呼叫兩階段 LLM，執行 joint action，render，寫 MP4 與 Excel | `open_excel`、`write_data`、module-level main loop |
| `llm_controller/` | LLM negotiation、per-CAV decision、prompt tools、scenario container、Chroma memory abstraction | `LlmAgent_negotiation_module`、`LlmAgent_action_module`、`PRE_DEF_PROMPT`、`DrivingMemory` |
| `highway_env/` | repository 內嵌且修改過的 `highway-env` fork；定義 Gym environments、road/lane、vehicle、observation、action、rendering、IDM/MOBIL | `AbstractEnv`、`IntersectionEnv`、`MergeEnv`、`HighwayEnv` |
| `videos&data/` | 已產出的 MP4 與 Excel，以及額外 comparison 結果說明；不是自動 evaluation code | `videos&data/Comparision.md` 與各 scenario result directories |
| `paper/` | 使用者提供的原始論文 PDF，目前未被 Git track | PDF |
| `README.md` | 只給 `pip install -r requirements.txt`、填入 API key、`python Run_multi_CAV_LLM.py` | Getting started |
| `requirements.txt` | 唯一 dependency manifest；只有部分套件 pin version，沒有 Python/CUDA/OS lock | 全檔 |

### 1.2 Environment / simulator 與 scenario definitions

Repository import `highway_env` 時，project root 的本地 package 會優先於 environment 中安裝的 PyPI `highway-env`。因此實驗語義由 repository 內 fork 決定，不應把 `highway-env==1.10.2` 當成實際 simulator implementation。

- Base lifecycle：`highway_env/envs/common/abstract.py::AbstractEnv.__init__` 會立即 `reset()`；`reset()` 建立 spaces/road/vehicles 並回傳舊 Gym 單一 `obs`；`step(action, env)` 回傳 `(obs, reward, terminal, info)`；`_simulate()` 在一個 policy step 內依 `simulation_frequency // policy_frequency` 推進 dynamics。
- Intersection：`highway_env/envs/intersection_env.py::IntersectionEnv` 建四向 unsignalized intersection；`MultiAgentIntersectionEnv.default_config()` hard-code 4 CAV。Observation 是 multi-agent `Kinematics`；action 是 joint `MultiAgentAction`，per-agent action 禁用 lateral control。背景車是 `IDMVehicle`，road 是 `RegulatedRoad`。
- Merge：`highway_env/envs/merge_env_v1.py::MergeEnv` 與 `MergeEnvMARL`；有 main road、merge lane、IDM HDVs、自訂 global reward。註冊為 `merge-v1` 與 `merge-multi-agent-v0`。
- Highway：`highway_env/envs/highway_env.py::HighwayEnv`；straight multi-lane road，預設 4 controlled vehicles 和 20 background vehicles。只註冊 `highway-v0` / `highway-fast-v0`，沒有明確命名的 multi-agent registration，但 default config 使用 multiple controlled vehicles。
- Roundabout：論文有此 scenario，repository 沒有 environment definition 或 registration。唯一文字出現在 `memory.py` 的註解 example。

### 1.3 LLM interface、prompt 與 cooperative logic

- Centralized negotiation：`llm_controller/llm_agent_negotiation_system.py::LlmAgent_negotiation_module.detect_conflicts()` 對 route samples 做幾何相交判斷；`send_to_chatgpt()` 將每個 pair 的 vehicle、speed、distance-to-conflict 送給一個 `gpt-4o-mini` call，要求產生 passing order。
- Distributed decision：`llm_controller/llm_agent_action.py::LlmAgent_action_module.llm_controller_run()` 逐一處理 controlled CAV；每台 CAV 都另外呼叫一次 `gpt-4o-mini`。
- Prompt construction：`llm_controller/prompt_llm.py` 不是 function-calling agent，而是一組 deterministic Python tools，先計算 available actions/lanes、lane vehicles、lane-change/current-lane/conflict safety，再由 `format_training_info()` 組成文字；`send_to_chatgpt()` 再串接 system role、traffic rules、cautions、memory placeholder、negotiation result 與 output format。
- Negotiation output parser：用 regex 假設 vehicle string 精確符合 `MDPVehicle #[0-9]+` 或 `IDMVehicle #[0-9]+`。
- Decision output parser：`extract_decision()` 用 substring 搜尋 `"decision": { ... }`，再依關鍵字判斷 semantic action；不是 JSON parser 或 schema validation。
- Action mapping：semantic action 經 `get_action_id_from_name()` 變成 ID；`MultiAgentAction.act()` 將 tuple 分派到每台 CAV；`MDPVehicle.act()` 更新 target lane / discrete target speed；`ControlledVehicle` 的 proportional steering/speed controllers 產生 low-level acceleration/steering；`Vehicle.step()` 更新 kinematic state。

### 1.4 Memory mechanism

- `llm_controller/memory.py::DrivingMemory` 使用 LangChain `OpenAIEmbeddings` 與 Chroma persistent store，實際 path 是 `./db/<env.spec.id>`。
- `retrieveMemory()` 執行 `similarity_search_with_score()` 並只回傳 metadata；`addMemory()` 將 scenario description 放在 `page_content`，將 negotiation/action/comments 放 metadata。
- Memory implementation 已存在，但目前 default execution path 明確對應 **Memory OFF**；後續 `Memory ON` experiment 需要顯式啟用既有 retrieval 與 augmentation calls：
  - `LlmAgent_action_module.send_to_chatgpt()` 把 `relative_memory(...)` 註解，直接令 `past_memory = ''`。
  - `llm_controller_run()` 把 `memory_update(...)` 註解。
  - `Run_multi_CAV_LLM.py` 仍在每個 policy step 建立 `DrivingMemory(env)`，可能初始化/讀取一個空的 `./db/...`；在 default Memory OFF path 中不把 retrieved memory 放入 prompt，也不新增 experience。
- Repository committed 的 `llm_controller/chroma/chroma.sqlite3` 並非 active code 的 path，兩者沒有接線證據。

### 1.5 Training / data generation / evaluation / logging

- 不需要、也沒有 LLM fine-tuning 或 policy training pipeline。所謂 continuous learning 是 RAG database online augmentation，不是更新 LLM weights。
- Active script 在同一 environment object 上跑 `range(100)` episodes。每 step 會有 1 次 negotiation LLM call，加上每台 controlled CAV 各 1 次 decision call；預設 intersection 是 4 CAV，因此約 5 calls/policy step。
- `open_excel()` 會建立 `./llm_controller/excel/` 和 episode workbook；`write_data()` 每 step 寫 vehicle position/speed/heading/background flag；`imageio` 寫 `./llm_controller/video/<episode>.mp4`。
- Active script 沒有 seed argument、CLI、configuration file、exception/retry/rate-limit handling、token/cost logging、prompt/response persistence或實驗 metadata。
- Code 會 print `llm_actions` 與 global reward，但沒有 paper 的 success rate、PET、travel velocity aggregation implementation。
- `videos&data/` 提供已生成 results，但無法從 repository 找到生成所有 paper tables/figures 或 comparison baselines 的 code。README 亦明示 comparison algorithms 不包含在內。

## 2. Paper method overview

Paper 將 cooperative driving 建模為 POMDP，CoDrivingLLM 由 environment、centralized-distributed reasoning、memory 三大模組構成。以下按指定 end-to-end chain 拆解。

| Stage | Paper 中的目的 | Input | Output | 使用 LLM | Training | Online update |
|---|---|---|---|---|---|---|
| Environment | 模擬 CAV/HDV dynamics，避免 LLM 直接做數值控制 | 前一時刻 states、CAV semantic actions、HDV actions | 新 vehicle states / feedback | 否 | 否；simulation interaction 提供 feedback | 每 simulation step 更新 state，但不更新 learned parameters |
| Observation | 在有限感知距離內表示周車；paper feature 為 `[x,y,vx,vy,lane,intent]` | Global state、sensor range | per-agent observation matrix `|N_i| x |F|` | 否 | 否 | 每 step 重算 |
| Cooperative Information | 對應 SAE J3216 state-sharing 與 intent-sharing；建立 lanes/leading/rearing/conflict vehicles 與 expected lane/speed | 每台 CAV observation、其他 CAV shared state/intent | scene description、conflict pairs | 主要是結構化/語意化資訊；paper 把其納入 LLM reasoning chain | 否 | 每 step 更新 shared state/intent |
| Prompt | 依 CoT 串接 scene、traffic rules、conflict severity、passing advice、安全檢查與 similar memories | State/intent、negotiation、memory | LLM input prompt | 否（prompt engineering 本身） | 否 | 每次 inference 動態生成 |
| LLM | 高階 world-knowledge reasoning，不負責精確數值運動 | Prompt | negotiation order 或 per-CAV semantic decision | 是；paper 使用 GPT-4o mini | 不 fine-tune | LLM weights 不更新 |
| Memory | RAG，使車輛避免重犯過去使 conflict 惡化的決策 | Previous scenario/conflict/action/outcome；current query | Vector database item；top similar few-shot experiences | Embedding/reasoning服務涉及 model，但不訓練 base LLM | 否 | 是；paper Algorithm 1 每 step 評估並 augment memory |
| Decision | 綜合 state、intent、central coordinator advice 與 memory；三層 action safety assessment | Scene prompt、negotiation、memories | `{SLOWER, IDLE, FASTER, LANE LEFT, LANE RIGHT}` | 是，每台 CAV distributed inference | 否 | 每 policy step inference |
| Vehicle Action | 將 semantic decision 映射 target speed/lane，再由 model-based controller 和 bicycle model執行 | Semantic action、current vehicle state | acceleration、steering、next state | 否 | 否 | controller/state 每 step 更新 |
| Evaluation | 衡量任務完成、安全、效率與 continuous learning | 多 seeds trajectories/results | success rate、PET、travel velocity；ablation/interaction-count curves | LLM method被評估，但 metric 本身不用 LLM | Comparison 中 MADQN 等可能需 training；CoDrivingLLM 本身不需 | Evaluation statistics 累積，非 policy parameter update |

Paper 的 Algorithm 1 順序是：所有 CAV 產生 scene descriptions → centralized coordinator 產生 conflicts → 每台 CAV 排序相關 conflict → retrieve memory → 組 prompt → distributed semantic decision → environment update → 評估 action impact 並寫入 memory。

## 3. End-to-end execution flow（repository active path）

1. Python import 本地 `highway_env`; `highway_env/envs/__init__.py` import 並註冊 merge、intersection、highway environments。
2. `Run_multi_CAV_LLM.py` 在 module import 時直接執行 `gym.make('intersection-multi-agent-v0')`，沒有 `if __name__ == '__main__'`。
3. `AbstractEnv.__init__()` 呼叫 `reset()`；之後每 episode 外層又呼叫 `env.reset()`。Intersection 預設建立 4 CAV 與背景 IDM vehicles。
4. 每 policy step 建立 `DrivingMemory(env)`；default execution path 是 Memory OFF：會初始化 Chroma/OpenAI embedding client，但 retrieval/update calls 未啟用。Memory ON experiment 需要顯式啟用既有 calls。
5. 建立 `LlmAgent_negotiation_module`：
   - 依 environment 名稱選 conflict participants；intersection 只看 controlled CAV，merge/highway 看 `env.road.vehicles`（含 HDV）。
   - 對 vehicle routes 各取 1,000 samples/lane，以 squared distance `< 1` 判斷路徑交會；intersection reaction range 50 m，merge/highway 120 m。
   - 送一個 centralized prompt 到 GPT-4o mini，取得各 pair passing order。
6. 建立 `LlmAgent_action_module`，逐 controlled CAV：
   - intersection speed 被直接截到 5 m/s；merge/highway 20 m/s。
   - regex 把 centralized output 轉成 ego-specific passing advice。
   - deterministic prompt tools計算 actions/lanes/near vehicles/TTC/TTCP safety。
   - `past_memory` 固定為空字串。
   - 送 per-CAV prompt 到 GPT-4o mini，substring parser取得 semantic action，映射成 ID。
7. Flatten actions 後呼叫 `env.step(tuple(action), env)`。
8. `MultiAgentAction` 分派 action；`MDPVehicle` 更新 target speed/lane；road 執行 IDM/MOBIL 背景車、controller 與 kinematics。
9. Environment 回傳舊式四元組；entry point render human 與 RGB frame、append MP4、逐 step save Excel。
10. CAV collision、全數抵達或 timeout 後 episode 結束，再 reset；總共 hard-code 100 episodes。

## 4. Paper-to-code mapping

| Paper Concept | Code File | Class / Function | Actual Implementation | Match Level |
|---|---|---|---|---|
| POMDP environment/state transition | `highway_env/envs/common/abstract.py` | `AbstractEnv.reset`, `step`, `_simulate` | 有 multi-agent state/action dynamics；API 為客製舊 Gym 且額外傳 `env` | Partially implemented |
| Finite-range observation `[x,y,vx,vy,lane,intent]` | `highway_env/envs/common/observation.py`; scenario configs | `KinematicObservation`; `default_config` | Kinematics 可輸出 position/velocity；intersection explicit features沒有 lane/intent，且 `observe_intentions=False` | Partially implemented |
| Mixed CAV/HDV simulation | `intersection_env.py`, `merge_env_v1.py`, `highway_env.py`; `vehicle/behavior.py` | vehicle creation; `IDMVehicle` | CAV 使用 `MDPVehicle`，HDV 使用 IDM/MOBIL | Fully implemented |
| Four paper scenarios | `highway_env/envs/` | environment registrations | Intersection、merge、highway存在；roundabout缺失 | Partially implemented |
| State-sharing | `llm_controller/prompt_llm.py` | `getAvailableLanes`, `getLaneInvolvedCar`, helper functions | 從 simulator global objects直接組 lane/vehicle描述；不是明確通訊層，亦未實作 paper 50 m ablation switch | Simplified |
| Intent-sharing | routes/destinations；`prompt_llm.py`; negotiation module | `record_route_xy`, prompt construction | 以已知 route/destination推算衝突，但沒有獨立 expected-lane/expected-speed message，intersection observation還關閉 intention | Partially implemented |
| Conflict pair detection | `llm_agent_negotiation_system.py` | `detect_conflicts`, `is_conflict`, `record_route_xy` | 以完整 planned routes sampling 相交並加 reaction range；1,000 points/lane 和距離門檻 hard-code | Hard-coded |
| `ΔTTCP` conflict severity thresholds 2/5/8 s | `llm_controller/prompt_llm.py` | `cal_ttcp`, `check_safety_with_conflict_vehicles` | 實作 2/5/8 thresholds；只對被建議 `passes second` 的 conflict計算，並假設 acceleration=2 | Partially implemented |
| Centralized conflict coordinator | `llm_agent_negotiation_system.py` | `send_to_chatgpt` | 單次 GPT call輸出 conflict pairs passing order；prompt沒有明列 paper traffic/social rules，僅要求 ensure safety | Partially implemented |
| Distributed per-CAV decision | `llm_agent_action.py` | `llm_controller_run`, `send_to_chatgpt` | 每台 controlled CAV獨立 GPT call，使用 ego prompt與 coordinator advice | Fully implemented |
| CoT: state → intent → negotiation → decision | `prompt_llm.py`, two LLM modules | prompt tools and calls | 流程分階段，但 state/intent多為 deterministic preprocessing；LLM只在 negotiation、decision被呼叫 | Partially implemented |
| Three-layer safety assessment | `prompt_llm.py` | `assess_lane_change_safety`, `check_safety_in_current_lane`, `check_safety_with_conflict_vehicles` | 有 current lane、adjacent lane、conflict lane三類文字安全分析；不是嚴格從 candidate set刪除 unsafe action，最終仍由 LLM遵循文字 | Partially implemented |
| Semantic five-action space | `prompt_llm.py`; `common/action.py`; `vehicle/controller.py` | `ACTIONS_ALL`, `DiscreteMetaAction`, `MDPVehicle.act` | 五個 IDs固定；intersection/merge decision module只允許 IDLE/FASTER/SLOWER | Fully implemented |
| Model-based low-level control | `vehicle/controller.py` | `ControlledVehicle.steering_control`, `speed_control` | proportional lane tracking與speed control存在 | Fully implemented |
| Paper bicycle model as active CAV dynamics | `vehicle/dynamics.py`; `vehicle/kinematics.py` | `BicycleVehicle`, `Vehicle.step` | `BicycleVehicle` class存在，但 discrete meta-action的 `vehicle_class` 是 `MDPVehicle`；active CAV走較簡化 kinematic `Vehicle.step`，不是此 bicycle class | Simplified |
| Gains `Ka=1.6`, `Kh=5` | `vehicle/controller.py` | `ControlledVehicle.KP_A`, `KP_HEADING`（需以 constants再核實） | 控制器架構相符；目前未找到明確 paper 命名的 `Ka`/`Kh` wiring 證據 | Unclear |
| Memory vector store | `llm_controller/memory.py` | `DrivingMemory` | Chroma + OpenAIEmbeddings persistent vector store存在 | Fully implemented |
| Memory retrieval / few-shot prompt | `memory.py`; `llm_agent_action.py` | `retrieveMemory`, `relative_memory`, `send_to_chatgpt` | Implementation exists；default execution path 將 call 註解並設 `past_memory=''`，因此是 Memory OFF。Memory ON experiment 需顯式啟用 `relative_memory(...)`，把 top-2 retrieved experiences注入 prompt | Partially implemented |
| Memory augment based on action outcome | `llm_agent_action.py` | `memory_update`, `generate_comment` | Implementation exists；default execution path 將 `memory_update(...)` call 註解，因此不寫入新 experience。Memory ON experiment 需顯式啟用此 call。既有評語由 hard-coded relation/action rules產生，且其是否完整對應 paper 所述「previous action outcome」仍需驗證 | Partially implemented |
| Online continuous learning | `memory.py`; `llm_agent_action.py`; `Run_multi_CAV_LLM.py` | `retrieveMemory`, `addMemory`, `relative_memory`, `memory_update` | Retrieval、augmentation與 prompt injection components 均存在；default command配置為 Memory OFF。顯式啟用兩個既有 calls 後形成 Memory ON path，但 outcome timing/semantics仍需忠實驗證 | Partially implemented |
| GPT-4o mini | both LLM modules | `client.chat.completions.create` | model string兩處 hard-code `gpt-4o-mini`，與 paper v3 implementation details一致 | Fully implemented |
| 20 different random seeds per scenario | paper only；`AbstractEnv.reset` | seed logic | reset可接受 testing seed，但 entry point不使用，反而 hard-code 100 episodes並自增 internal seed | Not found |
| Success criterion：all CAVs safe and reach destination | `intersection_env.py` | `_is_terminal`, `has_arrived` | environment可判斷 crash/arrival，但 entry point沒有統計 success rate | Partially implemented |
| PET metric | data only / paper | — | 找不到 metric calculation code | Not found |
| Travel velocity metric | `write_data` records speed | `write_data` | 原始速度寫入 Excel，但找不到 paper aggregate calculation | Partially implemented |
| Reasoning ablations | source/comments/data | — | 沒有 reproducible switches/commands對應關閉 state、intent、negotiation | Not found |
| Baseline comparisons | `videos&data/`; README | — | 只提供 outputs；README明示 iDFST/Cooperative Game/MADQN code不包含 | Not found |

## 5. Reproduction requirements

### 5.1 明示 requirements

| Requirement | Repository evidence | 結論 |
|---|---|---|
| Python | 沒有 `.python-version`、Conda YAML、`setup.py`、`pyproject.toml` 或 README version | **Unclear**；repository沒有宣告 Python version |
| Install command | README | `pip install -r requirements.txt` |
| Run command | README | `python Run_multi_CAV_LLM.py` |
| LLM/API | README + source | OpenAI Chat Completions + OpenAI embeddings；需有效 API key與網路 |
| Model | source + paper | `gpt-4o-mini` |
| Simulator | requirements + local source | 基於 `highway-env`，但 runtime實際使用 repository 內 fork |
| CUDA/GPU | 無 import/use 證據 | CoDrivingLLM active code不要求 local CUDA/PyTorch；embedding與chat均遠端 OpenAI |

`requirements.txt`：

| Package | Pinned version | Actual import/use |
|---|---:|---|
| `numpy` | unpinned | simulator、prompt math、actions |
| `openai` | `1.2.2` | `OpenAI` client |
| `gym` | `0.15.3` | environment API/registration/spaces |
| `matplotlib` | unpinned | `vehicle/dynamics.py` plotting utility |
| `pandas` | `1.3.5` | observations/road/vehicle data representation |
| `pygame` | unpinned | renderer |
| `langchain` | `0.0.335` | Chroma/OpenAIEmbeddings/Document imports |
| `imageio` | unpinned | MP4 writer |
| `imageio-ffmpeg` | unpinned | MP4 backend |
| `openpyxl` | unpinned | Excel logging |
| `highway-env` | unpinned | 安裝需求有列，但被 local `highway_env/` shadow |
| `chromadb` | `0.4.15` | vector store backend |
| `sentence-transformers` | `3.0.1` | active source沒有 import；可能是 Chroma ecosystem/實驗殘留 |
| `tiktoken` | unpinned | active source沒有直接 import；LangChain/OpenAI transitive use可能需要 |

Actual imports另有 `httpx`（在兩個 `send_to_chatgpt()` function內動態 import），但沒有直接列於 requirements；通常由 `openai` transitively安裝。Standard library imports包括 `os`, `re`, `json`, `random`, `typing`, `dataclasses`, `sqlite3`, `shutil`, `imageio` 等。

### 5.2 API key、environment variables、network 與 external files

- 沒有正式 environment-variable contract。兩個 LLM module都宣告 `api_key = "your key here"`；`memory.py` 另有 `api_key = 'your key here'` 並在 import 時覆寫 process 的 `OPENAI_API_KEY`。
- 兩個 chat modules都 hard-code `base_url="https://api.openai.com/v1"`。
- 兩個 chat modules都建立 `httpx.Client(proxies=...)`，proxy hard-code 為 `http://127.0.0.1:7890`。因此即使 API key正確，沒有該本機 proxy也可能失敗。
- Memory embedding同樣需要 OpenAI API；它沒有共用 chat client 的 proxy設定。
- Active memory path `./db/<environment-id>` 不存在於 baseline，正常初始化可能建立它；這是 runtime write，不是已附 external database。
- Committed `llm_controller/chroma/chroma.sqlite3` 存在，但 active code不讀它，schema/content也未在本階段修改或依賴。
- `llm_controller/video/` 存在；`llm_controller/excel/` 不存在但 `open_excel()` 會建立。
- 論文 comparison method source、roundabout environment、paper evaluation scripts、seed list與完整 experiment configs不在 repository。

### 5.3 Experiment commands 可重現程度

- README唯一 command：`python Run_multi_CAV_LLM.py`。
- 切換 scenario 必須手動編輯 entry script 的註解行；沒有 CLI（本階段禁止這種修改）。
- 沒有 paper「每 scenario 20 different seeds」、「0/2/5-shot」、「reasoning ablation」或 baseline comparison的公開 commands。
- 因此 README command 最多代表一個 hard-coded intersection data-generation/demo loop，不能視為完整 paper reproduction command。

## 6. Historical environment comparison：`codriving_yizhen`

本次只用 `conda list -n codriving_yizhen` 讀取 metadata，未啟動實驗或變更 environment。探測時 `conda run` 顯示：`The system cannot find the file specified.` 與 `Could Not Find E:\YiZhen\miniconda3\envs\codriving_yizhen\Library\etc\OpenCL\vendors\temp.txt`；Python本身仍能回報 3.8.20。此異常應獨立列為 environment integrity risk。

| Component | Repository requirement | Historical version | Classification | 理由 |
|---|---|---:|---|---|
| Python | 未宣告 | 3.8.20 | unclear | 無官方 version；但 pinned old stack大致屬 Python 3.8時代 |
| `openai` | 1.2.2 | 1.2.2 | compatible | 精確相符；API仍受服務端/model availability影響 |
| `gym` | 0.15.3 | 0.15.3 | compatible | 精確相符且 code採舊式 reset/step API |
| `highway-env` | unpinned | 1.10.2 | potentially problematic | local fork會 shadow installed package；若 path/order改變而載入 1.10.2，API與 scenario semantics很可能不同 |
| `gymnasium` | 未要求 | 1.1.1 | potentially problematic | source不用它；但與 `highway-env 1.10.2` ecosystem共存，誤 import/registration時可能出現 5-tuple API差異 |
| `numpy` | unpinned | 1.24.4 | probably compatible | code已使用 `np.int32`而非移除的 `np.int`；仍需 smoke test才確定 |
| `pandas` | 1.3.5 | 1.3.5 | compatible | 精確相符 |
| `langchain` | 0.0.335 | 0.0.335 | compatible | 精確相符；imports是該舊版 namespace |
| `chromadb` | 0.4.15 | 0.4.15 | compatible | 精確相符；existing DB/schema path另有問題 |
| `sentence-transformers` | 3.0.1 | 3.0.1 | compatible | 精確相符，但 active code未使用 |
| `httpx` | transitive/unpinned | 0.27.2 | probably compatible | `proxies=` 在此版本仍可用；不是 requirements direct pin，fresh install解析結果可能不同 |
| `imageio` | unpinned | 2.35.1 | probably compatible | API看似相符；FFmpeg/runtime codec待驗證 |
| `imageio-ffmpeg` | unpinned | 0.5.1 | probably compatible | 需實際 writer smoke test |
| `openpyxl` | unpinned | 3.1.5 | probably compatible | 使用基本 workbook API |
| `pygame` | unpinned | 2.6.1 | probably compatible | renderer API可能相容；Windows display/headless狀態待驗證 |
| `matplotlib` | unpinned | 3.7.5 | probably compatible | active entry不直接用 plot |
| `tiktoken` | unpinned | 0.7.0 | probably compatible | direct source未使用 |
| PyTorch | 未要求 | 2.4.1 | compatible | active method不依賴 local PyTorch；只可能被 unused sentence-transformers stack帶入 |
| CUDA runtime | 未要求 | 12.1 | compatible | active OpenAI backend不需 GPU；不應為 reproduction改 CUDA |
| `transformers` | 未要求 | 4.46.3 | compatible | active source未使用 |

總結：historical environment 對 repository明確 pinned stack高度接近，但不能因此判定可忠實重現。最大問題是 local-vs-installed `highway_env` ambiguity、environment 自身 OpenCL/temp 異常、API credentials/proxy，以及 paper功能/實驗 pipeline缺失，而不是 PyTorch/CUDA。

## 7. Likely reproduction risks（只分析，不修）

| Risk | Evidence / file / function | Expected problem | Possible minimal repair direction（待授權） |
|---|---|---|---|
| API key hard-coded placeholder | `llm_agent_action.py:9`; `llm_agent_negotiation_system.py:8`; `memory.py:7-8` | Authentication failure；memory import還覆寫既有 `OPENAI_API_KEY` | 統一從 environment variable讀取並禁止 source secret；先記錄原作者 API contract |
| Mandatory local proxy assumption | both `send_to_chatgpt()` use `127.0.0.1:7890` | Proxy未運行即 connection failure；shared machine proxy policy不明 | 將 proxy變成 optional config；未授權前不可改 Ollama/LLM backend |
| OpenAI service/model drift | hard-coded `gpt-4o-mini`; OpenAI API is remote | 2026 model behavior/version、availability、rate limits與原 paper runs不完全一致，結果可能 nondeterministic | 保存 exact model snapshot/parameters若服務支援；記錄 date、response、seed/temperature；不得擅換 model |
| No sampling controls | both chat calls只給 model/messages | server defaults可能變；無 temperature/seed/max token pin | 忠實確認原作者設定；若需 pin需先說明會改變 baseline |
| Fragile negotiation parser | `extract_vehicle_conflicts()` regex只認兩種 class-string格式 | LLM多 markdown、欄位順序變、JSON spacing/class display變即得到空 conflicts | 先保存 raw output；最小方向是 schema/JSON validation與受控 fallback，但須驗證不改 algorithm semantics |
| Fragile decision parser | `extract_decision()` substring；unknown回 `-1` | Format偏差可能產生 `None` 或 action `-1`，最後可能被當 Python negative index而執行錯誤 action | 加 strict validation/retry/fail-stop；不得偷偷替換 action |
| Memory experiment mode requires explicit activation | `relative_memory`/`memory_update` calls註解，`past_memory=''` | Default command執行的是 Memory OFF；若未記錄 activation狀態，可能把 Memory OFF結果誤標為完整 CoDrivingLLM或與 Memory ON結果混用。這是重要 experiment variable，不直接視為 repository defect | Reproduction protocol應明確分為 Memory OFF / Memory ON；Memory ON只顯式啟用既有 retrieval/augmentation calls，並記錄 database初始狀態、shots與feedback timing |
| Memory feedback timing/semantics不符 | `memory_update()`只依 prompt relation和當前 action hard-code comment；沒有 next-state outcome input | 即使取消註解，也未明確實作 paper「evaluate previous action impact」 | 需找原作者實驗版本；若缺失，明確列為不可復現，不自行發明 evaluator |
| Memory path mismatch | code `./db/<id>`；repo只有 `llm_controller/chroma/chroma.sqlite3` | 附帶 DB不被讀；active DB從空開始且位置依 cwd | 確認 intended DB與schema；建立明確 path/config前先備份 baseline |
| OpenAI embeddings on every step construction | `Run_multi...` 每 step `DrivingMemory(env)` | 重複 client/store initialization、cost/latency，且 placeholder key可能在 negotiation前先失敗 | 將 memory lifecycle提升到 episode/run scope只屬潛在工程修復；先確認原始行為 |
| Missing roundabout | no environment registration/file | 無法重現 paper 4-scenario claims與 roundabout curves | 尋找作者 commit/release/branch；不能用 unrelated architecture自行補造 |
| Missing evaluation pipeline | 無 PET/success/velocity aggregate code | 無法由 raw run重建 Table I/Figs且 success定義未自動統計 | 先根據 paper公式與 raw data驗證可否獨立重算；需 documentation/analysis implementation授權 |
| Missing baselines/ablations | README explicitly excludes comparison algorithms；無 ablation switches | 無法重跑完整 comparisons或 Fig. 5 | 取得原作者 code/config；保持 results-only與reproduced result區分 |
| Episode count/seed mismatch | paper 20 random seeds；script `range(100)`，reset用 internal increment | 統計 protocol與 paper不一致，且無 seed manifest | 取得 20 seeds；建立不改 semantics的 experiment harness需另行授權 |
| Old Gym custom API | `reset()->obs`; `step(action, env)->4-tuple`; requirement `gym==0.15.3` | Gymnasium/modern highway-env期待 `(obs,info)`與5-tuple；wrappers不相容 | 忠實環境應隔離舊 Gym stack，不先改成 Gymnasium；修復需 adapter且不得改 dynamics |
| Local/PyPI package name collision | local `highway_env/`; requirement also installs `highway-env` | import取決於 cwd/PYTHONPATH；不同 launcher可能用到 1.10.2 | 固定 project-root launch與記錄 `highway_env.__file__`；日後環境可避免不必要的 PyPI ambiguity |
| `highway-env` unpinned | requirements | fresh 2026 install取得新版及 Gymnasium dependencies | 忠實 reproduction應以 repository local fork為準並鎖 transitive versions；需先建立 clean env plan |
| `httpx` not direct pinned | dynamic import；historical 0.27.2 | fresh resolver可能取得不接受 `proxies=` 的版本，引發 `TypeError` | 先查 `openai==1.2.2`相容矩陣，之後 lock exact tested httpx |
| Output writes are heavy and non-atomic | workbook每 step `save`; MP4 100 episodes | slow I/O、partial/corrupt files、磁碟用量；非 long experiment階段不可執行 | reproduction harness再決定 checkpoint/logging，但不更改 metrics |
| Video directory assumptions | writer直接寫 existing `llm_controller/video`; Excel才自建 dir | 若 clean checkout缺資料夾/codec會在 run初期失敗 | preflight檢查 exact paths與FFmpeg，不自行跑 full experiment |
| No exception/retry/cost logging | entry + OpenAI calls | transient API failure中止整批；無法 audit exact calls/cost | 增加 reproducibility logging/retry需授權，且 retry可能改變 stochastic response |
| Mutation during analysis if imported | `Run_multi...` lacks main guard；import即跑；`memory.py` modifies env var | 看似 inspection/import可能觸發 API、file writes、100 episodes | 分析階段只讀 source，不 import entry；未來先加/使用 safe harness需授權 |
| Speed state directly clipped | `llm_agent_action.py:41` assigns `ego_veh.speed` | decision module直接改 simulator state，未透過 controller；可能與 paper environment transition不一致 | 先確認作者意圖；任何移除會改 scenario semantics，需研究確認與明確批准 |
| Intersection reward uses `self.vehicle.speed` | `IntersectionEnv._agent_reward()` | 所有 agent scaled speed可能取第一 controlled vehicle，而非 argument `vehicle` | 驗證 paper metric是否依賴 reward；修成 `vehicle.speed`會改 reward，必須先批准 |
| Merge is treated as “intersection” for actions | `get_actions()` sets `is_intersection=True` for merge | Merge禁止 lane change，即使 base `MergeEnv` lateral=True；可能與 paper five-action/merge semantics不一致 | 先比對原始 experiment behavior與影片；不可為了通過而自行開 lateral action |
| Lane-change safety implementation疑似不完整 | `assess_lane_change_safety()` visible path主要處理 left；right status初始化 True | right lane可能未被實際檢查，prompt卻報 safe | 完整 unit-level trace後再判斷修復；不得直接改 safety logic |
| TTCP data bug candidate | `most_dangerous_info['distance to conflict (others)']` 在 ego為 vehicle_i時寫入 vehicle_i distance | memory description可能使用錯方距離，影響 retrieval/feedback | 建構小型 read-only calculation test或人工 fixture驗證後才提 patch |
| Historical Conda integrity warning | `conda run` OpenCL `temp.txt` errors | 某些 native/OpenCL初始化或 `conda run`不穩定 | 保留 reference env不修改；未來另建 clean reproduction env前先做 environment inventory |
| Windows rendering/headless/codec | pygame human render + `imageio-ffmpeg` | shared Windows session、display、FFmpeg codec可能失敗 | 先做短 preflight（需下一階段授權），不改 simulator/render semantics |
| Encoding mojibake | README/source comments/column names顯示亂碼 | 文件、terminal與 possibly Excel labels不可讀；parser若碰非 ASCII可能不穩 | 確認 repository原始 encoding與 Git blob，不直接 re-encode source |

## 8. Unresolved questions

1. 本機 PDF是否正好對應 IEEE final version、arXiv v3，還是其他 revision？後續若可用安全 PDF extractor，應逐節比對 equations、figures與implementation details。
2. Paper experiments實際使用哪個 commit？目前 HEAD 2025-09-25 晚於論文/README多次更新；repository沒有 release/tag或 environment lock。
3. 作者執行 memory experiments時，究竟取消了哪些註解？是否另有未公開 feedback evaluator、seed list與預建 databases？
4. `llm_controller/chroma/chroma.sqlite3` 的 intended用途、collection name、embedding model與schema為何？為何 active path改為 `./db/<env-id>`？
5. Roundabout implementation與 raw results為何未包含？是否在 upstream歷史 commit、private branch或另一 repository？
6. Paper四場景的精確 vehicle counts、CAV/HDV比例、traffic density、duration、seed與destination configs是什麼？論文正文未完全列出，code defaults未必就是 paper settings。
7. GPT-4o mini run的 exact date/model snapshot、temperature、seed、token limits、retry policy與 prompt revision是什麼？
8. Paper intent-sharing的 `expected lane` / `expected speed` 在實驗 code中如何生成與交換？目前 code主要以 known route/destination替代，沒有獨立 message/state。
9. Paper三層 safety assessment稱 unsafe action會從 candidate set移除；目前 code看起來只把文字交給 LLM。是否有未公開 action masking版本？
10. Paper Eq. (2) gains與 Eq. (3) bicycle model是否真的用於 reported experiments？active discrete action path是 `MDPVehicle` + generic kinematic update。
11. `videos&data/` 中各目錄數字（例如 `2shot-90`、`5shot-80`）的命名、episode selection與 success label規則是什麼？
12. `codriving_yizhen` 的 OpenCL/temp warning是否只影響 `conda run` wrapper，或也影響直接 interpreter/native libraries？本階段不應修。
13. Comparison raw Excel 是否足以獨立重算 Table I 的 PET與velocity？需下一輪專門做只讀 data audit，且要先定義 paper metric公式與成功案例filter。

## 9. 第一階段結論

Repository 足以展示三個場景中的「centralized LLM passing-order negotiation + distributed per-CAV LLM semantic decision + modified highway-env control」主幹，但 **不能直接視為 paper 的完整 executable specification**。Memory retrieval與augmentation implementation已存在；default execution path選擇 Memory OFF，而後續 reproduction應把 Memory OFF / Memory ON視為明確的 experiment variable，並以顯式啟用既有 calls建立 Memory ON主要 baseline。其餘重要缺口仍是 roundabout缺失，以及 paper evaluation/ablation/baseline pipeline與20-seed protocol未提供。Historical environment對明示 pinned packages相當接近，但這不解決 method/protocol缺失，也不應以升降級或改 simulator semantics來掩蓋。

下一階段若獲授權進入 reproduction，合理順序應是：先凍結/識別 exact baseline與environment imports → 做不呼叫 API的最小 import/API preflight → 取得或確認 paper seed/config/memory artifacts → 只做必要且可追溯的 compatibility repairs → 先單 step/單 episode驗證 → 最後才執行完整 experiments。任何會改 reward、observation、action、scenario、LLM logic、memory feedback或metrics的變更，都必須另行說明並等待確認。
