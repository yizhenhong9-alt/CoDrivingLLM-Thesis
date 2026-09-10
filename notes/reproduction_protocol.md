# Phase 4A/4B - Full CoDrivingLLM Reproduction Protocol Audit

## 1. Scope and evidence

This document audits the experiment protocol only. It does not implement a new method, change simulator semantics, or authorize the 20-seed experiment.

Evidence used:

- IEEE Transactions on Vehicular Technology final paper, DOI `10.1109/TVT.2025.3552922`, especially Algorithm 1 and Section IV-A.
- Original released repository history through commit `f9e71fed08c1772cf4009ed61dfe91177019cf7d`.
- Current reproduction source at commit `720e7c95adfe017606b8375801eb28937afbd43b`.
- `Run_multi_CAV_LLM.py`, environment registrations/configuration, simulator RNG/termination code, Memory implementation, and Phase 2/3 controlled runners.

Important version distinction: the IEEE final paper contains four scenarios. The older arXiv text available in the existing Phase 1 notes described only three. This audit follows the IEEE final paper and records the version difference instead of replacing it silently.

## 2. Paper specification

The IEEE final paper states:

- Four scenarios: single-lane unsignalized intersection, roundabout, four-way highway, and merge.
- Base LLM: `GPT-4o mini`.
- Every scenario is repeated 20 times with different random seeds.
- The seeds randomize initial vehicle positions, speeds, and expected destinations.
- Success rate is the main performance indicator.
- A case is successful only when all CAVs finish their tasks safely and reach their destinations.
- The framework uses centralized conflict negotiation, distributed per-CAV decisions, environment transitions, and a persistent RAG Memory module.
- Algorithm 1 places environment transition before evaluation of the action impact and Memory augmentation.
- The final paper's continuous-learning experiment reports success rate against number of interactions; it does not provide a released seed list, exact Memory database initialization artifact, precise interaction-order protocol, or a complete aggregation command.
- PET and travel velocity are also reported for method comparison. The paper says safety/efficiency metrics in that analysis use successful cases only. It does not provide executable PET aggregation code in the repository.

## 3. Repository implementation audit

### 3.1 Scenario selection and run count

`Run_multi_CAV_LLM.py` selects a scenario by manually editing/commenting `gym.make(...)` lines:

```python
# env = gym.make('merge-multi-agent-v0', config=config)
env = gym.make('intersection-multi-agent-v0')
# env = gym.make('highway-v0')
```

There is no CLI scenario selector or four-scenario experiment matrix. The active script constructs one environment and then executes `for i in range(100)`, so it requests 100 episodes of the active intersection environment, not 20 episodes for each of four scenarios.

The script has module-level execution and no `if __name__ == "__main__"` guard. It must not be imported by an audit/test tool.

### 3.2 Seed behavior and RNG coverage

`AbstractEnv.default_config()` sets `seed: 0`. `AbstractEnv.__init__()` immediately calls `reset()`, which consumes seed 0 and increments `self.seed`. The first explicit `env.reset()` in the original episode loop therefore normally uses seed 1; subsequent loop resets increment sequentially. The effective original sequence is inferred to be seeds 1 through 100, but it is not explicitly recorded in outputs.

`AbstractEnv.reset()`:

- training/default branch seeds global `numpy.random` and Python `random` from `self.seed`;
- testing branch accepts `testing_seeds` and seeds the same two global RNGs;
- increments `self.seed` after every reset;
- assigns `self.np_random = numpy.random`, so most road/vehicle randomization uses the seeded global NumPy generator.

Problems:

- `AbstractEnv.seed(seeding)` ignores its `seeding` argument, calls `np.random.seed(self.seed)`, and returns `[None]`; it is not a reliable Gym seed contract.
- The original runner never records the effective seed or initial-state digest.
- No published 20-seed manifest exists.
- LLM sampling is not seeded or explicitly parameterized. Even with a deterministic simulator seed, a run is not fully deterministic.
- Process-global vehicle counters/identifiers may depend on earlier environment construction. Exact IDs are dynamically handled by the current prompts, but they should still be logged.
- Normal active source does not use PyTorch/transformers RNG. Gym-space RNG is not used for policy actions. Simulator RNG use is predominantly global NumPy plus Python `random`; future static checks must continue to reject any unseeded RNG newly introduced into an active environment path.

Minimum seed contract for a new runner:

1. Accept an explicit immutable list of 20 integer seeds.
2. Record the list and its order before execution.
3. For each case call `env.reset(is_training=False, testing_seeds=seed)` explicitly.
4. Re-record Python/NumPy seed, environment config, controlled-vehicle count, initial position/speed/destination/route state, and an initial-state hash.
5. Never infer a successful seed or rerun only failed seeds without retaining the original failed attempt.
6. Record that Ollama/provider sampling remains a separate nondeterministic source unless a later explicitly approved sampling contract is established.

### 3.3 Environment termination and success

Environment `terminal` and paper success are not equivalent.

- Intersection terminal: any controlled CAV crashes, all controlled CAVs arrive, duration limit, or optional off-road condition. `has_arrived()` is implemented. This scenario can support the paper success rule directly.
- Merge terminal: any controlled CAV crashes or duration limit. `has_arrived()` exists but all-arrived is not part of `_is_terminal()`.
- Highway terminal: only the first/default controlled vehicle crash, duration counter, or optional off-road condition. There is no scenario-specific `has_arrived()`/destination completion contract.
- Roundabout: no environment, registration, configuration, `has_arrived()`, or terminal implementation exists.

The original entry script accepts the environment terminal flag, prints reward, and closes the episode. It does not compute or aggregate the paper success predicate. A duration-limit episode is therefore not automatically a success.

Required success record per case:

```text
success = all CAVs are non-crashed
          AND all CAVs have verifiably completed their scenario task
          AND all CAVs have reached their destinations
```

This formula can be applied to intersection now. It must not be guessed for highway, merge, or the absent roundabout implementation. Scenario-specific task/destination evidence is required first.

### 3.4 Current metrics and output

Original `Run_multi_CAV_LLM.py` records:

- per-step vehicle `x`, `y`, speed, heading, and a controlled/background flag in `./llm_controller/excel/<episode>.xlsx`;
- rendered frames in `./llm_controller/video/<episode>.mp4`;
- global reward and actions only through console output.

It does not record/aggregate:

- explicit seed manifest;
- success/failure classification;
- terminal reason;
- all-CAV arrival flags;
- collision participants/timestamps;
- success rate over 20 cases;
- PET samples or aggregate PET;
- aggregate travel velocity;
- LLM request/response/model identity/latency;
- Memory mode, database state, retrievals, or writes;
- dependency/Git/environment identity.

Phase 2D/3B runners add robust JSON evidence for one episode, but neither is a four-scenario 20-seed experiment runner.

### 3.5 Memory control and persistence

Original released default behavior is Memory OFF even though `DrivingMemory(env)` is instantiated every policy step:

- retrieval in `send_to_chatgpt()` is commented and `past_memory = ''`;
- `memory_update()` in the per-CAV loop is commented.

If those existing calls are restored, all CAVs in a policy step share one `DrivingMemory` instance and one `./db/<environment-id>` Chroma collection. A new object is created every policy step, but the persistent path is shared across steps, episodes, and processes. Same-step writes are visible to later CAVs.

Current controlled runners expose explicit `Memory OFF`/`Memory ON`. Phase 3B starts from a fresh isolated database per run and preserves within-episode/same-step learning. This is suitable for functional validation but does not reproduce the original 100-episode cross-episode accumulation.

The IEEE continuous-learning protocol is incomplete: the paper relates success to interaction count, but neither the exact seed order nor the database checkpoint used at each interaction count is released. A reproducible local thesis protocol must declare its own controlled interpretation and must not label it as an exact unpublished paper protocol.

## 4. Four-scenario mapping

| Paper scenario | Repository environment candidate | Current state | Match / mismatch / unclear | Required change before 20-seed execution |
|---|---|---|---|---|
| Intersection | `intersection-multi-agent-v0` / `MultiAgentIntersectionEnv` | Registered; 4 CAV config; randomized positions/routes/destinations; all-arrived terminal exists; Phase 2/3 validated | Best available match. Controlled CAV speed is fixed at 5 m/s while other traffic speed is randomized; exact paper config/seed list remains unclear | Add explicit seed/config/success logging through a dedicated runner; do not change environment semantics |
| Roundabout | None | No source or registration; only a commented word in a Memory example | Missing | Obtain the authors' released/unreleased roundabout environment/config or formally implement separately as `Reconstructed Evaluation Infrastructure` with explicit approval. Do not substitute another environment silently |
| Highway | `highway-v0` / `HighwayEnv` | Registered; config says 4 controlled vehicles, but action/observation are single-agent; original entry comment proposes `highway-v0`; terminal observes only default vehicle and duration; no destination-arrival predicate | Incomplete/non-executable for the same four-CAV pipeline without configuration work; paper's “four-way highway” mapping is unclear | Static/single-step preflight a runner-supplied `MultiAgentAction`/`MultiAgentObservation` config; establish task/destination and all-CAV success semantics from author evidence before full runs |
| Merge | `merge-multi-agent-v0` / `MergeEnvMARL` | Registered multi-agent candidate; MARL config says 4 CAV, but density-3 `_reset()` forces `num_CAV = 3`; all destinations fixed to `d`; positions/speeds randomized; terminal excludes all-arrived | Partial mismatch | Resolve 3-vs-4 CAV discrepancy and define all-CAV arrival-based success. Any environment change requires explicit research-semantic approval |

## 5. Match / mismatch / unclear matrix

| Protocol item | Paper | Repository/current evidence | Status | Minimum required action |
|---|---|---|---|---|
| Scenarios | Four | Three candidate types; roundabout absent | Mismatch | Obtain/reconstruct roundabout explicitly |
| Runs per scenario | 20 | Active script runs 100 intersection episodes | Mismatch | Dedicated 20-seed matrix runner |
| Different random seeds | Required | Implicit increment; no manifest/log | Mismatch | Explicit seed list and per-case record |
| Positions randomized | Required | Present, scenario-dependent | Partial match | Record initial states and verify each scenario |
| Speeds randomized | Required | Partial: intersection controlled speed fixed; highway controlled speed fixed; merge randomized | Mismatch/unclear | Record exact behavior; obtain paper config before changing |
| Expected destinations randomized | Required | Intersection randomized; merge fixed; highway lacks comparable completion destination; roundabout absent | Mismatch | Scenario evidence/implementation required |
| Four CAVs | Paper implementation detail | Intersection/highway config 4; merge runtime forces 3; roundabout absent | Mismatch | Resolve merge and missing scenario |
| Success rule | All CAVs safe and arrive | Not aggregated; only intersection directly encodes all-arrived terminal | Mismatch | Explicit scenario-aware success evaluator |
| Success rate | Main metric | Not calculated | Missing | Aggregate successes / 20, retain every case |
| PET | Reported safety metric | No calculator | Missing | Later `Reconstructed Evaluation Infrastructure`, paper formula/evidence first |
| Travel velocity | Reported efficiency metric | Raw per-step speeds in Excel only | Partial | Define weighting/filtering and aggregate successful cases only |
| Centralized/distributed LLM | Required architecture | Present | Match for validated intersection | Preflight independently for each scenario |
| Memory learning | Persistent RAG concept | Components exist; released default calls disabled | Partial | Explicit mode and database lifecycle |
| Memory feedback timing | After environment outcome in Algorithm 1 | Released/current activated path updates before `env.step()` using heuristic | Mismatch | Document; do not silently repair |
| LLM model | GPT-4o mini | Thesis mode uses Ollama `qwen2.5:7b` | Adaptation | Separate Paper-Faithful and Local Thesis results |
| Exact experiment config | Implied by paper figures/text | No complete manifest | Unclear | Freeze every effective config field in artifact |

## 6. Remaining blockers to a faithful 20-seed reproduction

1. Roundabout implementation/configuration is missing.
2. No published 20-seed list or seed ordering is available.
3. Original seed API is non-standard and the active script does not record seeds.
4. Highway does not expose a validated four-CAV multi-agent action/observation path.
5. Highway lacks an all-CAV destination/task-completion predicate.
6. Merge forces 3 CAVs despite the paper stating 4 CAVs per environment.
7. Merge fixes every destination to `d`, contrary to the paper's general randomized-destination statement.
8. Merge terminal does not end on all-arrived.
9. Controlled initial speeds are not randomized in every scenario as the paper states generally.
10. The active script performs 100 episodes of one manually selected scenario, not a four-by-20 matrix.
11. No explicit success evaluator or 20-case success-rate aggregator exists.
12. PET computation/aggregation is absent.
13. Travel-velocity aggregation and successful-case filtering are absent.
14. Memory interaction-count/database checkpoint protocol is not released.
15. Released Memory feedback occurs before environment outcome, unlike Algorithm 1.
16. No exact paper Git tag/commit, complete environment config, seed manifest, LLM sampling snapshot, retry policy, or initial Memory database is published.
17. Local Thesis Mode uses Qwen and local embeddings, so it cannot be presented as exact GPT-4o-mini numerical reproduction.
18. LLM calls remain stochastic under provider-default sampling; simulator seeding alone is insufficient for bitwise replay.

## 7. Proposed minimum experiment runner changes

No large architecture change is recommended. Add a dedicated runner and aggregator rather than expanding `Run_multi_CAV_LLM.py`.

Proposed files, subject to a separate implementation approval:

- `scripts/phase4_reproduction_experiment.py`: one case per invocation, explicit scenario/seed/memory/backend/output arguments, based on the proven Phase 2D/3B loop.
- `scripts/phase4_aggregate_results.py`: read-only aggregation of completed case artifacts; never reruns or discards cases.
- Optional declarative `notes/phase4_seed_manifest.json`: fixed 20 integers and protocol version. This is reproduction infrastructure, not an inferred paper seed list.

Minimum runner contract:

```text
--scenario {intersection,roundabout,highway,merge}
--seed <int>
--memory-mode {off,on}
--database-path <absolute path; required only for on>
--output-root <absolute path>
--run-id <unique id>
--chat-backend / --chat-model / --chat-endpoint
--embedding-backend / --embedding-model / --embedding-endpoint
```

The runner should:

1. Fail closed for unsupported/missing scenario mappings.
2. Record Git status/commit, package versions, imported local `highway_env` path, complete effective config, seed, model digests, command, and timestamps.
3. Explicitly reset with the requested seed and capture initial states/routes/destinations.
4. Reuse the proven centralized negotiation and per-CAV decision path without fallback actions.
5. Preserve existing simulator/action/reward/Memory semantics unless a separately approved compatibility or research change is required.
6. Record every LLM call, parser result, action, reward, trajectory state, crash/arrival flag, terminal reason, and runtime.
7. Compute `success` only when the scenario has a verified all-CAV task/destination predicate; otherwise mark `success_status: unresolved` and fail the paper-scale protocol.
8. Never overwrite an existing run directory or database.
9. Write a success or failure artifact and preserve partial trajectories.
10. Avoid rendering/video during the primary metric run unless rendering is proven state-neutral; raw trajectories are the canonical evidence.

This runner is `Reconstructed Evaluation Infrastructure`. It must not be described as an original repository runner.

## 8. Four-scenario experiment matrix

Target paper-scale matrix after all blockers are resolved:

| Scenario | Environment ID/config | Seeds | Memory OFF | Memory ON | Cases per mode | Current readiness |
|---|---|---:|---|---|---:|---|
| Intersection | `intersection-multi-agent-v0` | same fixed 20 | independent cases, no DB | declared cumulative or independent DB policy | 20 | Ready for runner smoke test, not yet full batch |
| Roundabout | unavailable | same fixed 20 | blocked | blocked | 20 | Blocked: environment missing |
| Highway | candidate `highway-v0` plus unresolved multi-agent config | same fixed 20 | blocked | blocked | 20 | Blocked: action/terminal/success mapping |
| Merge | `merge-multi-agent-v0` | same fixed 20 | blocked | blocked | 20 | Blocked: actual CAV count and success semantics |

If both Memory modes are evaluated, the complete matrix contains `4 scenarios x 20 seeds x 2 modes = 160 cases`. This is a proposed matched reproduction matrix, not a claim that the paper explicitly reported a Memory OFF/ON 160-case factorial design.

## 9. Seed policy

- Use one versioned list of exactly 20 unique integers across all four scenarios and both Memory modes.
- Preserve the same scenario/seed pairing between Memory OFF and ON.
- Record execution order separately from seed identity.
- Do not replace failed seeds, cherry-pick successful seeds, or omit parser/backend failures.
- Prefer one process per case for fault isolation; record that object IDs may differ while physical initial-state values must match.
- Verify the reset by comparing initial-state artifacts between matched OFF/ON cases, not merely by comparing the requested seed.
- Because the original paper seed list is unavailable, label the manifest `reproduction seed set`, not `paper seeds`.

## 10. Memory ON/OFF policy

### Memory OFF

- `memory_mode="off"`.
- Do not instantiate or query a Memory database.
- Record database path as null and retrieval/update counts as zero.

### Memory ON

- Use the existing query, retrieval, prompt injection, feedback, update timing, and same-step visibility semantics.
- Use a database isolated by scenario, backend/embedding identity, protocol version, and experimental replicate.
- Never share a database between OpenAI and local embeddings or between scenarios.
- Record initial/final count, every retrieval/write, `top_k`, prompt insertion, and model digest.

Two distinct protocols must not be mixed:

1. `Independent-episode Memory ON`: fresh DB for every seed; measures within-episode Memory mechanics but not cross-interaction continuous learning.
2. `Cumulative-interaction Memory ON`: one initially empty scenario-specific DB persists through the declared 20-seed order; approximates released-code persistence and the paper's interaction-learning concept, but is order-dependent.

For paper continuous-learning claims, cumulative interaction is the closer available interpretation. It remains an explicit reconstruction because the paper does not release database checkpoints/order details. Matched Memory OFF/ON outcome comparison and continuous-learning curves should be reported as separate analyses.

## 11. Metrics policy

### Primary metric

For each scenario/mode:

```text
success_rate = successful_cases / 20
```

Every denominator case remains present even if it ends through crash, timeout, parser failure, backend failure, or unresolved task completion. Infrastructure failures should be separately categorized, not silently counted or excluded without a prespecified rule.

Required case fields:

- requested/effective seed and initial-state hash;
- success boolean or unresolved status;
- terminal reason;
- all-CAV crash and arrival/task-completion flags;
- episode steps, simulation time, total reward, runtime;
- full per-CAV trajectory and action history;
- LLM/parser/fallback counts and latency;
- Memory state/calls when enabled.

### PET and travel velocity

- Do not infer PET from reward.
- Preserve position/time trajectories at sufficient simulator resolution to reconstruct conflict-zone occupancy.
- Implement PET only after the exact definition, pair selection, collision handling, time resolution, and aggregation weighting are documented. Classify it as `Reconstructed Evaluation Infrastructure`.
- Define travel velocity weighting explicitly: per vehicle vs per timestep vs per case.
- For comparison with the IEEE table, calculate PET/travel-velocity aggregates over successful cases only, while retaining failed-case raw data and counts.

## 12. Output and logging policy

Recommended immutable layout:

```text
<output-root>/
  protocol.json
  seed_manifest.json
  <scenario>/
    <memory-mode>/
      seed_<seed>/
        case.json
        trajectory.jsonl
        chroma/              # Memory ON only, according to declared policy
  aggregate/
    case_index.json
    success_rate.json
    metrics.json
```

Requirements:

- All paths absolute; existing case directories fail closed.
- Atomic/checkpointed artifact writes.
- Store raw prompts/responses but never credentials or embedding vectors.
- Record schema/protocol version and SHA-256 for immutable manifests/artifacts.
- Preserve failed and partial cases.
- Aggregation reads artifacts only and never changes case data.
- Keep Paper-Faithful OpenAI and Local Thesis Ollama results in separate roots.

## 13. Exact proposed smoke-test procedure

No smoke test should run until the Phase 4 runner is separately approved and implemented.

1. **Static matrix validation**
   - Parse the four scenario mappings without importing `Run_multi_CAV_LLM.py`.
   - Require exactly 20 unique seeds in the manifest.
   - Verify OFF/ON pairs use identical seeds/configs except Memory fields.
   - Confirm roundabout/highway/merge unresolved mappings fail closed.

2. **Seed-reset preflight without LLM**
   - For intersection only, instantiate two fresh environments.
   - Reset both with one designated smoke seed via `is_training=False, testing_seeds=<seed>`.
   - Compare controlled/background positions, speeds, routes, destinations, and initial-state hashes.
   - Reset with a second seed and require a documented state difference.

3. **One deterministic simulator transition without LLM**
   - Use one explicitly recorded executable joint action.
   - Verify old Gym four-value API, local import path, reward, step counter, crash/arrival fields, and artifact writing.

4. **One Memory OFF integrated policy step**
   - One negotiation plus one decision per CAV.
   - Require valid parsers/action IDs, exactly one `env.step()`, zero Memory calls, and no fallback.

5. **One Memory ON integrated policy step with a fresh DB**
   - Verify initial count 0, sequential same-step retrieval/update, exact prompt insertion, write counts, and reopen persistence.
   - Keep feedback update before `env.step()` to match released code and label the paper discrepancy.

6. **One complete matched intersection pair**
   - Run one OFF case and one independent-episode ON case with the same smoke seed and effective config.
   - Verify identical initial-state hashes before comparing trajectories.
   - Treat this as functional validation only, not performance evidence.

7. **Two-seed aggregation dry run**
   - Aggregate two preserved case artifacts, including one synthetic/real failure category.
   - Verify denominator handling, success calculation, no dropped cases, and deterministic aggregate output.

8. **Scenario-specific gates**
   - Repeat steps 2-7 for merge/highway only after their multi-agent, arrival, and CAV-count blockers are resolved.
   - Roundabout remains blocked until an evidence-supported environment exists.

9. **Approval gate**
   - Review all smoke artifacts, effective configs, seed manifest, Memory protocol, and failure policy.
   - Only then request explicit approval for the full 20-seed batch.

## 14. Audit conclusion

The current repository can support a controlled intersection reproduction and provides partial merge/highway components, but it cannot yet execute a faithful four-scenario, 20-random-seed IEEE reproduction. Roundabout is absent, highway/merge success semantics and multi-CAV configuration are incomplete, and the original repository lacks seed manifests and metric aggregation.

The minimum safe next implementation is a fail-closed, one-case-at-a-time Phase 4 experiment runner plus a read-only aggregator. Environment or success-semantic repairs for roundabout, highway, and merge must be reviewed separately because they may constitute research-semantic changes or reconstructed evaluation infrastructure.

## 15. Phase 4C implementation: intersection-only case runner

Phase 4C implements the approved intersection-only portion of the audited protocol. It does not add execution support for roundabout, highway, or merge and does not alter `Run_multi_CAV_LLM.py`.

Added files:

- `scripts/phase4_reproduction_experiment.py`: one case per invocation, fail-closed runner.
- `scripts/phase4_aggregate_results.py`: artifact-only, read-only aggregator.
- `notes/phase4_seed_manifest.json`: fixed local reproduction seed manifest.

The runner CLI contract is:

```text
python -m scripts.phase4_reproduction_experiment \
  --scenario intersection \
  --seed <integer> \
  --memory-mode <off|on> \
  --output-root <absolute-path> \
  --run-id <unique-directory-safe-id> \
  [--ollama-endpoint http://127.0.0.1:11435] \
  [--chat-model qwen2.5:7b] \
  [--embedding-model nomic-embed-text:latest] \
  [--timeout 120]
```

Only `intersection` is accepted. Every invocation explicitly calls `env.reset(is_training=False, testing_seeds=<seed>)`, runs exactly one episode, refuses an existing run directory, and records the actual Git/runtime/model/environment provenance. The model tags are resolved through Ollama inventory and their digests are stored. Simulator seed reproducibility does not imply LLM determinism; sampling remains provider-default and is recorded as nondeterministic.

## 16. Phase 4C artifact schema and lifecycle

Each case uses this immutable layout:

```text
<output-root>/intersection/memory_<off|on>/seed_<seed>/<run-id>/
  case.json
  trajectory.jsonl
  llm_calls.jsonl
  memory_events.jsonl       # Memory ON only
  chroma/                   # Memory ON only
```

`case.json` uses schema `phase4c.case.v1` and protocol `phase4c-intersection-v1`. It is checkpointed atomically and preserves both completed and failed runs. It records the complete effective environment config, all initial controlled/background vehicle states, a stable initial-state SHA-256, seed/reset provenance, terminal classification, explicit per-CAV success predicates, reward/time/step totals, LLM/parser counters, Memory counters, package versions, local `highway_env` path, and resolved model identity. No credentials or embedding vectors are stored.

`trajectory.jsonl` records initial, policy-step-end, and available simulator-substep vehicle states: position, speed, heading, lane, route, destination, controlled/background role, crash/arrival state, and selected controlled action. `llm_calls.jsonl` stores each lossless prompt/request, raw response, parsed result, transport/parser status, identity, and latency. No automatic retry or fallback action is introduced. `memory_events.jsonl` records retrieval query, `top_k`, retrieved metadata/scores, exact prompt-section validation, update payload/counts, and final reopen; it never records vectors.

The known declared Gym action-space discrepancy is recorded as a counter rather than treated as a new fatal condition. As in the validated Phase 2D/3B path, execution is fail-closed against the original per-agent executable action maps. This does not repair or redefine the released action space.

Memory OFF never imports or constructs `DrivingMemory`; database path and Memory activity are zero/null. Memory ON always uses a new `chroma/` directory within the fresh case directory. It preserves the released/current Phase 3B sequence: one shared Memory instance within each policy step, sequential per-CAV retrieval/decision/update with same-step visibility, and update before `env.step()`. The known IEEE Algorithm 1 versus released-code feedback timing discrepancy remains unchanged.

Intersection success is evaluated separately from generic termination: every controlled CAV must be non-crashed, satisfy `IntersectionEnv.has_arrived()`, and therefore have completed its intersection task. Missing arrival evidence fails closed.

## 17. Phase 4C read-only aggregation

The aggregator accepts an absolute `--input-root` and one `--memory-mode`. It only reads `case.json`, invokes no simulator/LLM/Memory component, emits JSON to stdout, rejects incompatible schema/protocol/scenario records, rejects incomplete matching artifacts instead of omitting them, and rejects duplicate completed cases for the same seed/mode. Both unsuccessful completed episodes and infrastructure/backend/parser/Memory failures remain in the denominator. PET is explicitly not calculated.

Example:

```text
python -m scripts.phase4_aggregate_results \
  --input-root E:\YiZhen\phase4_results \
  --memory-mode off
```

## 18. Phase 4C seed manifest

`notes/phase4_seed_manifest.json` defines exactly 20 unique positive integer seeds under the name `reproduction_seed_set`:

```text
104729, 130363, 155921, 181081, 205759,
230431, 256019, 281117, 306491, 331777,
357059, 382457, 407893, 433291, 458789,
484181, 509687, 535123, 560617, 586009
```

This list was fixed before Phase 4C outcome observation and is intended for matched Memory OFF/ON cases. It is not the paper's unpublished seed list.

## 19. Phase 4C local validation result

Validation on `2026-09-08` used no Ollama, GPU, LLM call, Chroma database, or complete episode.

- Both scripts compiled and their `--help` interfaces loaded without runtime dependencies.
- An unsupported scenario was rejected by CLI argument validation.
- The manifest contained exactly 20 unique integers and the declared schema/protocol/name.
- Using an existing Python `3.8.20` environment, two fresh intersection environments reset with seed `104729` produced the same test snapshot hash; seed `130363` produced a different hash.
- After the seed check passed, exactly one simulator-only transition used joint action `(1, 1, 1, 1)`. It returned the repository's four-value Gym API, advanced `env.steps` to `1`, returned reward `0.0`, and did not terminate.
- The imported simulator path was repository-local: `C:\Thesis\CoDrivingLLM-Thesis\highway_env\__init__.py`.

The smoke-test hash was computed by the validation command over positions, speeds, headings, routes, destinations, and controlled/background flags. The runner records a richer canonical initial-state payload and its own SHA-256 at runtime; matched OFF/ON cases must compare that runner-generated value.

## 20. Phase 4C limitations and next gate

The matched Phase 4C Lab RDP smoke pair has now completed with seed `104729`. Memory OFF and Memory ON recorded the same `initial_state_sha256`, so both cases began from the same simulator state. Both episodes completed through the runner and terminated with a controlled-vehicle crash; these two trajectories are functional validation evidence, not evidence of Memory performance improvement. The Memory ON case completed `34` policy steps and `136` per-CAV decisions, retrievals, updates, and successful writes, ending with `final_count=136` in its fresh isolated database.

Roundabout remains blocked because the released repository has no corresponding environment. Highway and merge remain blocked for paper-scale reproduction by the scenario/configuration, multi-CAV, and success/arrival issues documented above. Resolving those items is outside Phase 4C and may require separately reviewed Reconstructed Evaluation Infrastructure or research-semantic decisions. The 20-seed batch remains unapproved and unexecuted.

## 21. Phase 4D Memory semantics freeze

### 21.1 IEEE conceptual Memory behavior

The IEEE paper describes Memory augmentation as outcome-aware: a CAV makes a decision, the environment transitions to the next state, the impact of the decision is evaluated, and the resulting experience is added to Memory. Algorithm 1 therefore gives the conceptual order:

```text
decision
→ environment transition
→ impact evaluation
→ memory augmentation
```

The surrounding text emphasizes actions that intensify conflicts, negative feedback, and avoiding repeated mistakes. However, the paper does not publish an executable failure-only storage rule, exact experience schema, exact `top_k`, interaction order, seed order, database checkpoint procedure, reset policy, or evaluation-write policy. The emphasis on failed experiences must not be converted into an undocumented exclusive storage condition.

### 21.2 Released-code Memory behavior

The released entry path constructs `DrivingMemory` with the persistent scenario path `./db/<environment-id>`, but retrieval and update are commented out by default. When the repository-provided Memory calls are restored, the operational behavior is:

```text
for each controlled CAV in order:
    construct current prompt information
    retrieve with the last two prompt_info lines and top_k=2
    inject formatted retrieved metadata into the per-CAV prompt
    obtain and parse the LLM decision
    generate heuristic feedback from the current relation and action ID
    append one Chroma record unconditionally
after all CAVs:
    env.step(joint_action, env)
```

The feedback does not compare pre-action and post-action states and does not observe reward, collision, arrival, or episode success. There is no explicit failure-only filter, success label, or negative-experience label. A record is appended for every activated per-CAV decision, including the `Conflict info is empty` branch. This released-code update-before-`env.step()` behavior conflicts with the ordering shown in IEEE Algorithm 1 and is intentionally preserved and documented rather than silently repaired.

### 21.3 Phase 3B/4C independent-episode behavior

Phase 3B and Phase 4C preserve the activated released-code query, `top_k=2`, Chroma similarity-search flow, prompt injection format, heuristic `generate_comment()` feedback, unconditional per-decision append, same-step sequential visibility, and update-before-`env.step()` timing. Their experimental isolation policy differs from the released persistent default: every case uses a fresh independent database and never reuses another case's Memory.

In the matched Phase 4C Memory ON smoke, `34` policy steps with `4` controlled CAVs produced:

```text
34 × 4 = 136 decisions
136 retrievals
136 update calls
136 successful writes
final_count = 136
```

This multiplication is the behavior of the activated released-code per-CAV loop. It is not proven to be the exact storage frequency used for the paper because the paper does not define whether one interaction or one stored experience corresponds to a policy step, a CAV decision, an episode, or another unit.

### 21.4 Frozen storage decision

The Phase 4D decision is:

```text
INSUFFICIENT EVIDENCE — DO NOT CHANGE YET
```

The current unconditional per-CAV storage behavior must remain unchanged for released-code reproduction. Failure-only storage must not be introduced without a separately proposed and approved research-semantic reconstruction defining the failure level, post-action evaluator, attribution window, positive-experience policy, and validation procedure.

## 22. Frozen Memory experiment protocols

### Protocol A — Memory OFF

- No `DrivingMemory` construction, retrieval, update, write, or database path.
- Answers the performance and trajectory question for CoDrivingLLM without Memory augmentation.
- Provides the matched baseline for identical scenario seeds and initial-state hashes.

### Protocol B — Independent-episode Memory ON

- Every seed/episode starts from its own fresh isolated database.
- Preserves released-code within-episode and same-step Memory behavior.
- Answers whether the activated released mechanism changes behavior within a matched episode without contamination from earlier seeds.
- Suitable for matched Memory OFF/ON comparison, but not sufficient to reproduce the cross-interaction learning claim in Fig. 7.
- Each case must log its database path, initial/final counts, model and embedding digests, ordered retrieval/write events, seed, and initial-state hash.

### Protocol C — Reconstructed cumulative-interaction Memory ON

- One initially empty, scenario-specific database persists across a predeclared ordered seed/interaction sequence.
- Conceptually closer to the continuous accumulation shown in Fig. 7 than Protocol B.
- Must be classified as `Reconstructed Continuous-Interaction Infrastructure`, not the exact paper protocol.
- Exact reproduction is not justified because the paper does not publish interaction order, seed order, database checkpoints, reset/clear policy, or whether evaluation interactions write back into Memory.
- Results are order-dependent because each retrieval depends on all earlier stored records and same-step CAV writes may be visible to later CAVs.
- Before implementation, the interaction unit, accumulation/evaluation split, evaluation-write policy, checkpoint schedule, scenario/model/database identity, and failure preservation policy require separate approval.

## 23. Phase 4D scope boundary

The IEEE conceptual outcome-aware evaluator and the activated released-code heuristic evaluator are distinct behaviors. Protocols A and B reproduce and isolate released/current code behavior. Protocol C may reconstruct the paper's continuous-learning concept, but it does not resolve the Algorithm 1 timing mismatch or the unpublished failure-only question. No protocol may be called the exact paper Memory protocol without additional evidence.

## 24. Phase 4E intersection three-seed mini validation

### 24.1 Scope and matched initial states

Phase 4E completed a three-seed Lab RDP mini validation for `intersection` using Protocol A (Memory OFF) and Protocol B (independent-episode Memory ON). The reproduction seeds and matched runner-generated initial-state hashes were:

| Seed | Memory OFF/ON `initial_state_sha256` |
|---:|---|
| `104729` | `c482bbb24668d5171f409c574ae66e6821f0d7a214ba161328daaba3352a5851` |
| `130363` | `f3df5aa82c40d5fd21f1a9b8ae2d5b837731470b3c435e57e0b8923d90147215` |
| `155921` | `e3a580f43600d217d8afd9d119c180ab3671cb65fe1bb30b9afa52a996ca3212` |

For every seed, the OFF and ON cases had the same initial-state hash. Different seeds produced different hashes. This validates matched initial simulator state construction for the mini set; it does not make Ollama/LLM sampling deterministic.

### 24.2 Memory OFF evidence

| Seed | Runner status | Success | Terminal reason |
|---:|---|---:|---|
| `104729` | `completed` | `false` | `controlled_vehicle_crash` |
| `130363` | `completed` | `false` | `controlled_vehicle_crash` |
| `155921` | `completed` | `true` | `all_controlled_vehicles_arrived` |

The canonical OFF aggregate was:

| Metric | Value |
|---|---:|
| Total discovered cases | `3` |
| Successful cases | `1` |
| Failed/unsuccessful cases | `2` |
| Success rate | `0.3333333333333333` |
| Mean episode steps | `57` |
| Median episode steps | `41` |
| Mean simulation time | `11.355555555555554 s` |
| Median simulation time | `8.2 s` |
| Mean wall-clock runtime | `235.54091813333335 s` |
| Median wall-clock runtime | `197.3143661 s` |
| Mean LLM calls per case | `285` |
| Median LLM calls per case | `205` |

All canonical OFF cases recorded zero parser failures, zero fallback actions, and zero Memory retrieval/update/write activity.

Seed `104729` has an earlier failed smoke artifact caused by the released-code `env` argument mismatch documented in Attempt 17. That artifact remains preserved as historical debugging evidence. The canonical completed OFF case is `phase4c_smoke_off_seed104729_retry1`; the earlier failed attempt must not be overwritten or treated as the canonical completed case.

For OFF aggregation, a staging directory containing only the canonical `case.json` artifacts was used because the smoke/debug root contains both the original failed `104729` attempt and its canonical completed retry. This staging directory is aggregation-only infrastructure: it selects preserved canonical artifact records for the read-only aggregator and is not experimental data, a rerun, or a replacement for the source artifacts.

### 24.3 Independent-episode Memory ON evidence

| Seed | Runner status | Success | Terminal reason |
|---:|---|---:|---|
| `104729` | `completed` | `false` | `controlled_vehicle_crash` |
| `130363` | `completed` | `true` | `all_controlled_vehicles_arrived` |
| `155921` | `completed` | `true` | `all_controlled_vehicles_arrived` |

The Memory ON aggregate was:

| Metric | Value |
|---|---:|
| Total discovered cases | `3` |
| Successful cases | `2` |
| Failed/unsuccessful cases | `1` |
| Success rate | `0.6666666666666666` |
| Mean episode steps | `73.33333333333333` |
| Median episode steps | `89` |
| Mean simulation time | `14.577777777777778 s` |
| Median simulation time | `17.733333333333334 s` |
| Mean wall-clock runtime | `363.7404639 s` |
| Median wall-clock runtime | `452.9575356 s` |
| Mean LLM calls per case | `366.6666666666667` |
| Median LLM calls per case | `445` |

Memory accounting examples were:

| Seed | Decisions | Retrievals | Updates | Successful writes | Final count |
|---:|---:|---:|---:|---:|---:|
| `130363` | `388` | `388` | `388` | `388` | `388` |
| `155921` | `356` | `356` | `356` | `356` | `356` |

All ON cases used independent-episode Memory, started with an empty database, recorded zero parser failures and zero fallback actions, and ended with a final database count equal to successful writes. No new Memory semantics were introduced: the released-code retrieval, heuristic feedback, unconditional per-decision write, same-step visibility, and update-before-`env.step()` behavior remained preserved.

### 24.4 Interpretation boundary

Phase 4E is a mini pipeline and stability validation. Its purpose is to validate multi-seed execution, matched OFF/ON initial simulator states, explicit success classification, artifact preservation, Memory accounting, and multi-case aggregation.

Three seeds are insufficient for paper-level or thesis-level performance conclusions. In particular, the observed `66.7%` Memory ON versus `33.3%` Memory OFF success rates must not be reported as evidence that Memory improves performance. Ollama sampling is not guaranteed deterministic, and the sample is too small for an effect estimate. Paper/code Memory fidelity differences remain documentation-only; Phase 4E does not resolve or modify them.

### 24.5 Next gate

The next step is not automatically the full 20-seed execution. Before a formal intersection batch:

1. complete the original GitHub experiment-parameter audit;
2. freeze every experiment parameter and its evidence/classification;
3. use a clean formal output root containing no smoke/debug retries or staging artifacts;
4. review the frozen protocol and obtain explicit approval for the 20-seed intersection batch.
