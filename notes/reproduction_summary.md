# CoDrivingLLM Reproduction Summary

## Phase 2A — Controlled Environment and Simulator Smoke Reproduction

- Status: simulator-only smoke baseline passed on `2026-08-24`.
- Repository baseline: branch `master`, HEAD `f9e71fed08c1772cf4009ed61dfe91177019cf7d`.
- Reproduction environment: `E:\YiZhen\conda_envs\codriving_repro`, Python `3.8.20`, pip `24.2`.
- Local simulator confirmed: `E:\YiZhen\Thesis\CoDrivingLLM-Reproduction\highway_env\__init__.py`.
- Registered environments confirmed: `intersection-multi-agent-v0`, `merge-multi-agent-v0`, and `highway-v0`.
- Intersection smoke result: `gym.make()`, explicit `reset()`, and one valid four-CAV joint `IDLE` step succeeded without rendering or LLM calls.
- Compatibility fix: one `DataFrame._append()` call was changed to `DataFrame.append()` to match repository-pinned `pandas==1.3.5`. No observation data construction arguments or research semantics were changed.
- Memory OFF status: not tested in Phase 2A.
- Memory ON status: not tested in Phase 2A.
- Remaining limitations: LLM configuration/API, parser behavior, complete episodes, memory semantics, evaluation infrastructure, repeated seeds, and paper-level metrics remain untested and must not be inferred from this smoke result.

## Phase 2B — Ollama Backend

- Mode: `Local Reproduction / Thesis Mode`; results must not be described as exact GPT-4o-mini reproduction.
- Backend status: minimal transport adaptation and both single-call smoke tests passed on `2026-08-25`.
- Ollama: version `0.32.9`; session-local endpoint `http://127.0.0.1:11435`; model store `E:\YiZhen\ollama_models` without persistent environment changes.
- Available models: `qwen2.5:7b`, `llama3:latest`, and `nomic-embed-text:latest`.
- Selected model: `qwen2.5:7b` (7.6B, `Q4_K_M`).
- GPU status: GPU 0 was idle before inference and loaded only the selected model; no other process was terminated or changed.
- Centralized negotiation status: one call succeeded; raw request/response saved.
- Negotiation parser status: original `extract_vehicle_conflicts()` parsed the response without modification.
- Per-CAV decision status: one first-CAV call succeeded; raw request/response saved.
- Decision parser status: original `extract_decision()` returned `IDLE`, mapped to action ID `1`, without modification.
- Additional dependencies: none; standard-library HTTP transport was used.
- OpenAI path: preserved as the default backend and lazy-loaded only when selected.
- Prompt/parser changes: none.
- Remaining limitations: provider defaults differ and were not equalized; results are not GPT-4o-mini numerical reproduction; no full episode, memory path, repeated seed, or evaluation was run.

## Phase 2C — Integrated Single-Step Test

- Mode: `Local Reproduction / Thesis Mode`, Ollama `qwen2.5:7b`, Memory OFF.
- Status: exactly one integrated policy step passed on `2026-08-25` after two preserved blocked attempts.
- Environment: real reset state from `intersection-multi-agent-v0`, four controlled CAVs, configured seed field `0`.
- Approved interface adaptation: negotiation prompt dynamically restricts output to current exact vehicle identifiers and presents both ordering forms neutrally. Parser remained unchanged.
- Successful negotiation: actual identifiers parsed; latency about `1.019s`.
- Four per-CAV decisions: `FASTER`, `IDLE`, `FASTER`, `IDLE`; all original parsers/action mappings succeeded.
- Joint action: `(3, 1, 3, 1)`.
- Environment transition: one step; reward `0.0`; terminal `False`; no CAV crash; all agent dones false.
- Memory: database not instantiated, retrieval/update count `0`.
- Complete episodes: `0`.
- Known discrepancy: declared `Discrete(3)` space rejects IDs `3/4`, while executable original `ACTIONS_LONGI` and entry path use IDs `4/1/3`. This was documented, not repaired.
- Research-semantic changes: none beyond the explicitly approved provider-interface prompt clarification.

## First Complete Ollama Episode

- Mode: `Local Reproduction / Thesis Mode`; this is not an exact GPT-4o-mini numerical reproduction.
- Status: one complete Memory OFF episode finished on `2026-08-25`; no batch or second episode was run.
- Configuration: `intersection-multi-agent-v0`, configured seed field `0`, Ollama `qwen2.5:7b`, endpoint `http://127.0.0.1:11435`, provider-default sampling controls.
- Pipeline: centralized negotiation, four distributed per-CAV decisions, unchanged parsers, original semantic action mapping, and `env.step()` ran for every policy step.
- Episode result: 43 policy steps; cumulative reward `-2.5`; terminal reason `controlled_vehicle_crash`; controlled crash flags `[True, True, False, False]`; arrival flags `[False, False, False, False]`.
- Calls/parsers: 43 negotiation calls and 172 decision calls; negotiation parser failures `0`; decision parser failures `0`; no fallback action.
- Runtime/latency: episode runtime `313.427s`; recorded LLM latency `245.292s` (`66.817s` negotiation and `178.475s` decisions).
- Action-interface discrepancy: declared Gym space rejected 30 of 43 original-mapped joint actions, but all 43 were present in the executable action dictionaries and executed successfully. No action-space modification was made.
- Crash status: the Python experiment process completed normally; the terminal crash was a simulator outcome.
- Artifact: `notes/artifacts/phase2d/full_episode_memory_off.json`, SHA-256 `83C1A91102761159CCA9E26B88572BDD9337C3CE10F386E2BAF12F396B79462D`.
- Research-semantic changes: none during this episode milestone. The previously approved Ollama/Qwen2.5 exact-identifier interface prompt adaptation remained active.
- Remaining limitations: this is one trajectory only and provides no statistical performance claim. Memory ON, repeatability, multi-seed evaluation, and paper-level metrics remain untested.

## Phase 3A — Local Memory ON Preflight Implementation

- Status: source implementation and isolated Lab server runtime verification passed before Phase 3B preparation.
- Classification: Ollama local embedding is a `Local Reproduction / Thesis Memory Mode adaptation`, not original OpenAI embedding behavior.
- Original/reference path: `DrivingMemory(env)` still defaults to `OpenAIEmbeddings`; the OpenAI import is lazy and there is no automatic backend fallback.
- Local path: an explicit Ollama embedding adapter implements the synchronous `embed_query()` / `embed_documents()` interface and targets `/api/embed` using Python standard-library HTTP/JSON support.
- Memory semantics preserved: original query construction, `top_k=2`, Chroma similarity search, stored `page_content`, metadata schema, prompt injection format, `generate_comment()`, and pre-`env.step()` update timing were not changed.
- Preflight runner: requires an unused absolute database path, resolves and records the model digest, performs one empty-store retrieval through the decision prompt, one decision, one original memory update, a `0 -> 1` count check, same-process reopen, and a second retrieval. It never calls `env.step()` and refuses database reuse.
- Dependencies: the Lab server validated `langchain==0.0.335`, `chromadb==0.4.15`, `tokenizers==0.13.3`, and `posthog==3.8.4`; `openai` and `tiktoken` are not required for the explicit local branch. `posthog==4.2.0` failed during Chroma initialization on Python 3.8, while `posthog==3.8.4` passed with no broken requirements.
- Static verification: Python syntax compilation, a mocked no-network Ollama adapter contract test, static invariant checks, and `git diff --check` passed. No Ollama, GPU, network, database, simulator step, or episode was executed.
- Pre-commit review fixes: the runner now requires an explicit existing preflight root and enforces strict database containment while rejecting repository `db`/`llm_controller/chroma` roots; validates semantic action and executable ID before update; records failed runtime stage/type/message/checkpoints and re-raises; closes the environment in `finally`; and requires exact Memory-section, query, `top_k`, reopen-count, and metadata assertions before success.
- Runtime result: `nomic-embed-text:latest` returned `768`-dimensional embeddings; the isolated database changed `0 -> 1`, reopened with count `1`, and successfully retrieved the written experience. Artifact status was `success`.
- Remaining limitation: this validates Memory mechanics only, not a full Memory ON trajectory or performance improvement; the known original feedback-timing discrepancy remains unchanged.

## Phase 3B — First Controlled Full Memory ON Episode Preparation

- Status: runner prepared locally; the full episode has not been executed.
- Intended difference from Phase 2D: Memory ON retrieval, exact prompt injection, and original pre-`env.step()` update are enabled with a fresh isolated Chroma database. Negotiation, parser, action mapping, simulator, reward, observation, scenario, and terminal semantics remain aligned with Phase 2D.
- Configuration: `intersection-multi-agent-v0`; Ollama `qwen2.5:7b`; Ollama `nomic-embed-text:latest`; endpoint supplied explicitly at runtime; provider-default sampling.
- Instrumentation: records model digests, initial/final memory counts, every retrieval and retrieved count, exact prompt insertion, every update and verified count increment, actions, parser failures, fallback count, rewards, terminal outcome, crash/arrival flags, LLM and embedding calls/latencies, and total runtime.
- Scope: exactly one functional-validation/trajectory-observation episode. It must not be interpreted as evidence that Memory ON improves performance.
- Server Attempt 1: stopped at policy step `0` after one negotiation call because `qwen2.5:7b` serialized the otherwise correct exact-ID object as a quoted/escaped JSON string inside the output list. Decision, embedding, retrieval, update, and `env.step()` counts remained `0`; this is an Ollama/Qwen negotiation output-format issue, not a Memory failure.
- Attempt 1 compatibility clarification: the negotiation prompt now requires actual JSON object list elements, explicitly forbids quoted/escaped object strings, and shows dynamic Correct/Incorrect examples built from the current real conflict identifiers. The original exact-ID parser and all research semantics remain unchanged.

## Phase 4C — Intersection Reproduction Runner and First RDP Blocker

- Phase 4C runner status: the intersection-only one-case runner and read-only aggregator are implemented. The first Lab RDP Memory-OFF smoke used run ID `phase4c_smoke_off_seed104729`, seed `104729`, and initial-state SHA-256 `c482bbb24668d5171f409c574ae66e6821f0d7a214ba161328daaba3352a5851`.
- First smoke failure: `TypeError: inference() missing 1 required positional argument: 'env'` occurred before the first environment transition in the current-lane acceleration safety path. The failed artifact is retained and must not be overwritten.
- Root cause/classification: original released-code signature/call-site mismatch plus a previously unexercised latent path. This is a `Compatibility / Runtime Repair`, not a Phase 4C-only regression or Research-Semantic Change.
- Minimal repair: thread the existing `prompt_engineer()` `env` argument through `check_safety_in_current_lane()` and into the already declared `isAccelerationConflictWithCar.inference(..., env)` argument. No other safety-tool call or safety computation was changed.
- Matched smoke status: Lab RDP revalidation subsequently completed for both Memory OFF and independent-episode Memory ON using seed `104729`. Both artifacts recorded the same `initial_state_sha256`; both episodes completed and terminated with a controlled-vehicle crash. This is functional/trajectory evidence only, not a Memory performance claim.
- Memory ON evidence: `34` policy steps, `4` controlled CAVs, `136` decisions, `136` retrievals, `136` updates, `136` successful writes, and `final_count=136` in a fresh isolated database. The `34 × 4` storage count follows activated released-code behavior and is not proven to be the paper's exact experience frequency.

## Phase 4D — Memory Semantics Documentation Freeze

- IEEE conceptual order: `decision → environment transition → impact evaluation → memory augmentation`. The paper emphasizes negative feedback for actions that intensify conflict but does not publish an exclusive failure-only rule or an executable outcome evaluator.
- Released/current code order: per-CAV retrieval using the final two `prompt_info` lines with `top_k=2`; prompt injection; decision; heuristic `generate_comment()` feedback; unconditional per-decision Chroma append; then `env.step()`. Feedback does not observe the post-action state, reward, collision, arrival, or episode outcome, and there is no failure-only filter.
- Phase 3B/4C fidelity: independent-episode Memory ON preserves the activated released-code semantics while using a fresh isolated database for each case. The known Algorithm 1 versus released-code update-timing mismatch remains unchanged.
- Frozen decision: `INSUFFICIENT EVIDENCE — DO NOT CHANGE YET`. Do not introduce failure-only storage without a separately approved research-semantic reconstruction.
- Protocols: A = Memory OFF; B = independent-episode Memory ON; C = `Reconstructed Continuous-Interaction Infrastructure` with one initially empty scenario-specific database carried through a declared ordered sequence.
- Fig. 7 limitation: Protocol C is conceptually closer to continuous learning, but cannot be called the exact paper protocol because interaction order, seed order, database checkpoints, reset policy, and evaluation-write policy are unpublished.
