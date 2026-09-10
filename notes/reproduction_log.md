# CoDrivingLLM Reproduction Log

## Attempt 1

- Date/time: `2026-08-24` (`Asia/Taipei`)
- Goal: Create the isolated `codriving_repro` base environment.
- Command: `conda create -n codriving_repro python=3.8.20 pip=24.2 -y`
- Environment: Conda base `E:\YiZhen\miniconda3`, Conda `26.3.2`
- Expected behavior: Create a Python 3.8.20 environment without changing `codriving_yizhen`.
- Actual behavior: Creation stopped before the environment transaction.
- Error/output: `CondaToSNonInteractiveError` for the configured Anaconda default channels.
- Root cause: Conda attempted to use configured channels whose Terms of Service had not been accepted.
- Proposed fix: Use per-command `--override-channels -c conda-forge`; do not accept ToS or modify global channel settings.
- Files affected: None.
- Semantic impact: Compatibility provisioning only; no research-semantic impact.
- Test result: Failed before creation.

## Attempt 2

- Date/time: `2026-08-24` (`Asia/Taipei`)
- Goal: Create the base environment while avoiding changes to global Conda configuration.
- Command: `conda create -n codriving_repro --override-channels -c conda-forge python=3.8.20 pip=24.2 -y`
- Environment: Conda base `E:\YiZhen\miniconda3`, Conda `26.3.2`
- Expected behavior: Create `codriving_repro` with Python 3.8.20 and pip 24.2.
- Actual behavior: Environment was created at `C:\Users\yizhen0925\.conda\envs\codriving_repro` because that path is first in `envs_dirs`.
- Error/output: No creation error. A premature `conda run` check briefly returned `DirectoryNotACondaEnvironmentError` while the transaction was still completing; verification succeeded after transaction completion.
- Root cause: Name-based creation followed Conda's configured `envs_dirs` order; the C: user environment directory precedes `E:\YiZhen\miniconda3\envs`.
- Proposed fix: Remove the unused C: environment and recreate using an explicit E: prefix.
- Files affected: The temporary Conda environment only.
- Semantic impact: Compatibility provisioning only; no research-semantic impact.
- Test result: Python `3.8.20` and pip `24.2` were verified before relocation was requested. The interrupted dependency installation installed no target packages.

## Attempt 3

- Date/time: `2026-08-24 17:45:47 +08:00`
- Goal: Remove the unused C: environment and recreate it at `E:\YiZhen\miniconda3\envs\codriving_repro`.
- Commands:
  - `conda env remove --prefix C:\Users\yizhen0925\.conda\envs\codriving_repro -y`
  - `conda remove --prefix C:\Users\yizhen0925\.conda\envs\codriving_repro --all --override-channels -c conda-forge -y`
  - `conda create --prefix E:\YiZhen\miniconda3\envs\codriving_repro --override-channels -c conda-forge python=3.8.20 pip=24.2 -y`
- Environment: Current account `DESKTOP-ISTRFAC\yizhen0925`; Conda base `E:\YiZhen\miniconda3`
- Expected behavior: Recreate the environment at the exact E: prefix and verify Python/pip before dependency installation.
- Actual behavior: The first removal command hit the default-channel ToS check and made no change. The override-channel removal succeeded. Explicit-prefix creation on E: failed before the transaction.
- Error/output: `CondaError: Unable to create prefix directory 'E:\YiZhen\miniconda3\envs\codriving_repro'. Check that you have sufficient permissions.`
- Root cause: `E:\YiZhen\miniconda3\envs` is owned by `DESKTOP-ISTRFAC\nclab`. The current account has `ReadAndExecute` but no directory creation permission there.
- Proposed fix: Have the directory owner/administrator create the exact child directory and grant the current account write access to that child, or obtain explicit authorization for a scoped ACL change. An alternative writable E: prefix requires user approval because it differs from the requested path.
- Files affected: The temporary C: `codriving_repro` environment was removed; no E: environment was created. `codriving_yizhen` was not modified.
- Semantic impact: Compatibility provisioning only; no source or research-semantic change.
- Test result: Blocked before environment creation and before package installation.

## Attempt 4

- Date/time: `2026-08-24 17:53:55 +08:00`
- Goal: Create `codriving_repro` at a user-writable E: prefix and stop before simulator dependency installation.
- Commands:
  - Writable-directory test under `E:\YiZhen\conda_envs`
  - `conda create --prefix E:\YiZhen\conda_envs\codriving_repro --override-channels -c conda-forge python=3.8.20 pip=24.2 -y`
  - `conda run --prefix E:\YiZhen\conda_envs\codriving_repro python --version`
  - `conda run --prefix E:\YiZhen\conda_envs\codriving_repro python -m pip --version`
- Environment: Conda base `E:\YiZhen\miniconda3`, Conda `26.3.2`
- Expected behavior: Create an isolated environment at the exact writable prefix with only Python 3.8.20, pip 24.2, and Conda runtime packages.
- Actual behavior: Parent write test and environment creation succeeded. `conda env list` reports the exact prefix.
- Error/output: None. The transaction completed successfully.
- Root cause: Not applicable. The alternative prefix avoids the parent-directory ACL that blocked Attempt 3.
- Proposed fix: No further provisioning fix required.
- Files affected: New Conda environment at `E:\YiZhen\conda_envs\codriving_repro`; reproduction documentation updated.
- Semantic impact: Compatibility provisioning only; no source or research-semantic change.
- Test result: `sys.prefix` is `E:\YiZhen\conda_envs\codriving_repro`; Python is `3.8.20`; pip is `24.2`. No simulator, LLM, or memory packages were installed.

## Attempt 5

- Date/time: `2026-08-24 18:03:16 +08:00`
- Goal: Install and verify minimal simulator dependencies, confirm local imports and Gym registration, then execute one simulator-only intersection step.
- Commands:
  - `conda run --prefix E:\YiZhen\conda_envs\codriving_repro python -m pip install gym==0.15.3 numpy==1.24.4 pandas==1.3.5 pygame==2.6.1 matplotlib==3.7.5`
  - Exact-prefix package/import/registry preflight commands
  - Minimal `gym.make('intersection-multi-agent-v0')`, reset, and one-step diagnostic command
- Environment: `E:\YiZhen\conda_envs\codriving_repro`; Python `3.8.20`; pip `24.2`
- Expected behavior: Instantiate the repository-local intersection environment, reset it, inspect its multi-agent spaces and vehicles, and advance one valid `IDLE` joint action.
- Actual behavior:
  - All five exact pins installed successfully; `pip check` reported no broken requirements.
  - `openai`, `langchain`, `chromadb`, and `ollama` are absent.
  - `highway_env` imported from `E:\YiZhen\Thesis\CoDrivingLLM-Reproduction\highway_env\__init__.py`.
  - `intersection-multi-agent-v0`, `merge-multi-agent-v0`, and `highway-v0` were all registered with the expected repository entry points.
  - The first smoke command did not execute Python because Conda 26.3.2 cannot wrap a multiline `python -c` argument. Direct use of the verified environment interpreter bypassed only that command-transport limitation.
  - `gym.make('intersection-multi-agent-v0')` then failed during constructor-internal `reset()` before the requested external reset or step could run.
- Error/output:
  - Command transport: `NotImplementedError: Support for scripts where arguments contain newlines not implemented.` A secondary Conda reporter error was `KeyError('user_agent')`.
  - Simulator construction: `AttributeError: 'DataFrame' object has no attribute '_append'` at `highway_env/envs/common/observation.py:208` in `KinematicObservation.observe()`.
- Root cause: The repository pins `pandas==1.3.5`, which provides the public `DataFrame.append()` API but not the private `DataFrame._append()` API used at line 208. The same function already uses `DataFrame.append()` at line 219. This is an internal repository code/dependency-pin incompatibility.
- Proposed fix: Compatibility Fix — replace only `df._append(...)` with `df.append(...)` at `highway_env/envs/common/observation.py:208`, retaining the same records, columns, `ignore_index=True`, observation shape, and ordering. Test by rerunning only the single constructor/reset/step smoke test. Do not change the pandas pin or observation semantics.
- Files affected: No source file was modified. Reproduction documentation only.
- Semantic impact: No research semantics changed. The proposed source change is not applied and is classified as a minimal Compatibility Fix because it restores the API available in the repository-pinned pandas version without changing data content or observation design.
- Test result: Import and registration preflights passed; simulator reset and one-step smoke remain blocked pending approval of the proposed Compatibility Fix.

## Attempt 6

- Date/time: `2026-08-24 18:09:37 +08:00`
- Goal: Apply the approved single-line pandas Compatibility Fix and rerun the minimal intersection simulator smoke test.
- Command: Direct invocation of `E:\YiZhen\conda_envs\codriving_repro\python.exe` from the repository root; import local `highway_env`, call `gym.make('intersection-multi-agent-v0')`, explicit `env.reset()`, and one `env.step((1, 1, 1, 1), env)`.
- Environment: `E:\YiZhen\conda_envs\codriving_repro`; Python `3.8.20`; `gym==0.15.3`; `numpy==1.24.4`; `pandas==1.3.5`
- Expected behavior: Restore pandas 1.3.5 compatibility without altering observation content or design, then instantiate, reset, and advance the original simulator by one policy step.
- Actual behavior:
  - `gym.make()` succeeded with environment type `MultiAgentIntersectionEnv` and spec ID `intersection-multi-agent-v0`.
  - Explicit `reset()` succeeded and returned `numpy.ndarray`, shape `(4, 25)`, dtype `float64`.
  - Declared observation space was `Tuple(Box(5, 5), Box(5, 5), Box(5, 5), Box(5, 5))`.
  - Action space was `Tuple(Discrete(3), Discrete(3), Discrete(3), Discrete(3))`.
  - Four controlled vehicles and three background vehicles were present among seven road vehicles.
  - Joint `IDLE` action `(1, 1, 1, 1)` passed `action_space.contains()`.
  - One step succeeded and returned a four-element tuple: observation `numpy.ndarray` shape `(4, 25)`, reward `numpy.float64(0.0)`, terminal `False`, and an info dictionary.
  - Info keys were `agents_dones`, `cav_crashed`, `cost`, and `speed`.
- Error/output: No runtime error. Git warned that LF may be replaced by CRLF if Git later touches the source file; the exact diff contains only the approved one-line method-name change.
- Root cause: Resolved incompatibility between repository-pinned `pandas==1.3.5` and the unsupported private `DataFrame._append()` call.
- Proposed fix: Applied exactly as approved: `df._append(...)` to `df.append(...)` at `highway_env/envs/common/observation.py:208`.
- Files affected: `highway_env/envs/common/observation.py`, `notes/reproduction_environment.md`, `notes/reproduction_log.md`, and `notes/reproduction_summary.md`.
- Semantic impact: Compatibility Fix only. Records, columns, ordering, `ignore_index=True`, observation space, scenario, vehicles, actions, reward, and all other source logic were unchanged.
- Test result: Phase 2A import, registration, reset, and one-step simulator smoke test passed. No LLM, Ollama, memory, rendering, full episode, or Phase 2B work was executed.

## Attempt 7

- Date/time: `2026-08-25 09:50:29 +08:00`
- Goal: Inventory the existing Ollama installation and models before selecting a backend model or modifying source.
- Commands:
  - `where.exe ollama`
  - `ollama --version`
  - `ollama list`
  - localhost `GET http://127.0.0.1:11434/api/tags`
  - localhost `GET http://127.0.0.1:11434/api/version`
- Environment: Repository HEAD `304b1ef555a9dcb181173428013a1faebb110d5d`; reproduction prefix `E:\YiZhen\conda_envs\codriving_repro`; execution mode `Local Reproduction / Thesis Mode`
- Expected behavior: Verify the installed Ollama client/service and enumerate existing local models without installation, update, deletion, or model download.
- Actual behavior:
  - Executable was found at `C:\Users\yizhen0925\AppData\Local\Programs\Ollama\ollama.exe`.
  - The first sandboxed CLI call could not connect and could not write its AppData log. The localhost API initially refused the connection.
  - A user-approved non-sandboxed read-only inventory allowed the existing Ollama application/service to start. API version `0.32.9` was then reachable at `127.0.0.1:11434`.
  - Both `ollama list` and `/api/tags` reported no installed models.
  - The application reported that a newer installer exists, but no update was performed.
- Error/output:
  - Initial sandboxed call: `Error: timed out waiting for server to start` after `failed to create server log ... Access is denied.`
  - Initial API call: connection refused at `127.0.0.1:11434`.
  - Final model inventory: header only (`NAME ID SIZE MODIFIED`) and `{"models":[]}`.
- Root cause: The initial startup failure was caused by sandbox restrictions on the Ollama AppData log path. After startup outside the sandbox, the blocking condition is an empty local model inventory.
- Proposed fix: Do not pull automatically. The user must decide which model to prepare outside this controlled step; after a model exists, rerun inventory, record its exact tag/size/quantization where available, execute `nvidia-smi`, then implement and validate the minimal transport adaptation.
- Files affected: Reproduction documentation only. No source or Conda environment package changes.
- Semantic impact: None. No prompt, parser, simulator, decision, conflict, memory, or backend source logic changed.
- Test result: Blocked by no suitable local model. No inference, GPU workload, backend modification, negotiation call, or per-CAV call was attempted.

## Attempt 8

- Date/time: `2026-08-25 10:05:41 +08:00`
- Goal: Point a session-local Ollama service at the existing E: model store, implement the minimal dual backend, and run exactly one negotiation plus one per-CAV decision call.
- Commands:
  - Launch hidden child service with process-scoped `OLLAMA_MODELS=E:\YiZhen\ollama_models` and `OLLAMA_HOST=127.0.0.1:11435`.
  - Verify `/api/version`, `/api/tags`, `ollama list`, and `nvidia-smi`.
  - Syntax/import preflight with `E:\YiZhen\conda_envs\codriving_repro\python.exe`.
  - Failed invocation: `python scripts/phase2b_llm_smoke.py`.
  - Successful invocation: `python -m scripts.phase2b_llm_smoke`.
- Environment: repository HEAD before changes `304b1ef555a9dcb181173428013a1faebb110d5d`; Python `3.8.20`; Ollama `0.32.9`; mode `Local Reproduction / Thesis Mode`.
- Expected behavior: Preserve OpenAI and prompt/parser contracts while substituting only Ollama transport, then validate both original parsers with one call each.
- Actual behavior:
  - Session-local endpoint `127.0.0.1:11435` exposed all three existing models without moving or downloading data.
  - GPU 0 was idle before inference; GPU 1 had only desktop/graphics activity. Ollama subsequently placed `qwen2.5:7b` entirely on GPU 0.
  - Backend syntax/import preflight passed without installing `openai`, `httpx`, `langchain`, or `chromadb`.
  - Direct script-file invocation failed before any LLM request because Python put `scripts/` rather than repository root on `sys.path`.
  - Module invocation succeeded. Centralized negotiation made one call; its original regex parser found the single conflict decision for both involved CAV perspectives.
  - Only after negotiation parser success, the first controlled CAV made one decision call. Original `extract_decision()` returned `IDLE`; original action mapping returned ID `1`.
- Error/output:
  - Invocation-only failure: `ModuleNotFoundError: No module named 'highway_env'` for `python scripts/phase2b_llm_smoke.py`. No request occurred. Correct command is module execution from repository root.
  - Negotiation raw content included a Markdown JSON fence, the requested decision object, and extra prose. Parser succeeded without modification.
  - Decision raw content included explanatory prose followed by `"decision": {"IDLE"}`. Parser and action mapping succeeded without modification.
- Root cause: The only runtime failure was Python script-path import resolution, corrected solely by invocation form. No backend or research logic defect was involved.
- Proposed fix: Use `python -m scripts.phase2b_llm_smoke` from repository root. No source compatibility fix was needed after backend implementation.
- Files affected: `llm_controller/llm_backend.py`, `llm_controller/llm_agent_negotiation_system.py`, `llm_controller/llm_agent_action.py`, `scripts/phase2b_llm_smoke.py`, Phase 2B documentation, and two JSON result artifacts.
- Semantic impact: Transport/interface adaptation only. Prompts, centralized/distributed architecture, conflict detection, parsers, action mapping, simulator, reward, observation, scenario, safety logic, and memory logic were not changed.
- Test result:
  - Negotiation: success; model `qwen2.5:7b`; latency about `35.537s`; original parser success.
  - Decision: success; same model; latency about `0.761s`; semantic action `IDLE`; mapped action ID `1`; original parser success.
  - No environment step, complete episode, Memory OFF/ON experiment, or additional LLM call was run.

## Attempt 9

- Date/time: `2026-08-25 10:16:49 +08:00`
- Goal: Execute exactly one integrated real-state policy step: intersection environment, centralized negotiation, four per-CAV decisions, joint action, and one environment transition.
- Command: `E:\YiZhen\conda_envs\codriving_repro\python.exe -m scripts.phase2c_integrated_single_step`
- Environment:
  - Repository HEAD before changes: `dab161d6ea9a623ebb36bafeb90946e5c8b2c6bc`
  - Environment ID: `intersection-multi-agent-v0`
  - Backend/model: Ollama `qwen2.5:7b` at `http://127.0.0.1:11435`
  - Mode: `Local Reproduction / Thesis Mode`
  - Memory mode: `Memory OFF`; no database instantiated, retrieval count `0`, no update
  - Configured simulator seed field: `0`
- Expected behavior: Parse one centralized negotiation response, obtain four valid original semantic actions/action IDs, assemble the original joint action, and call `env.step()` exactly once.
- Actual behavior:
  - Environment creation/reset succeeded with four controlled vehicles.
  - One centralized negotiation call completed in about `6.593s` for the real conflict pair `MDPVehicle #624` / `MDPVehicle #48`.
  - Ollama returned literal generic identifiers `"i"` and `"j"` rather than the actual simulator vehicle identifiers.
  - Original `extract_vehicle_conflicts()` returned no conflicts for all four CAVs.
  - The runner stopped before any per-CAV request, joint action, or `env.step()`.
- Error/output: `RuntimeError: Original negotiation parser did not parse the Ollama response`. Raw response and exact message/API response are stored in `notes/artifacts/phase2c/integrated_single_step.json` (SHA-256 `F67105207D3634395D2D925D598707EBFEDD6D71747364179DAE1CC01CDEEBBA`).
- Root cause: Model output-format failure. Although the prompt included actual vehicle strings in the conflict description, `qwen2.5:7b` copied generic `i`/`j` labels into the requested output fields. The original parser intentionally accepts only exact `MDPVehicle #[0-9]+` or `IDMVehicle #[0-9]+` identifiers.
- Proposed fix: Requires user decision. Options are an interface prompt clarification that inserts actual IDs into the format example, or a parser interpretation for generic labels. The latter risks guessing/mapping behavior and must not be implemented silently. No prompt or parser change was applied.
- Files affected: Added `scripts/phase2c_integrated_single_step.py`, the blocked-run JSON artifact, and reproduction documentation. No existing prompt, parser, backend, or simulator source was modified.
- Semantic impact: None in the attempted run. The proposed remedies may affect prompt or parser semantics and therefore require explicit approval.
- Test result: Phase 2C blocked at centralized negotiation parsing. LLM call count `1`; per-CAV calls `0`; environment step count `0`; no complete episode was run.

## Attempt 10

- Date/time: `2026-08-25 10:22:32 +08:00`
- Goal: Apply the approved dynamic exact-identifier prompt clarification and retry the integrated single-step test.
- Command: `E:\YiZhen\conda_envs\codriving_repro\python.exe -m scripts.phase2c_integrated_single_step`
- Environment: Same controlled Phase 2C configuration as Attempt 9; Memory OFF; artifact `integrated_single_step_retry1.json`.
- Expected behavior: Require `qwen2.5:7b` to use current real vehicle identifiers, allow the unchanged regex parser to succeed, obtain four actions, and execute one step.
- Actual behavior:
  - The dynamically generated prompt listed only the actual conflict identifiers, prohibited generic identifiers/placeholders, and showed both possible exact-ID orderings without recommending one.
  - Negotiation returned actual identifiers `MDPVehicle #616` and `MDPVehicle #776`; original parser succeeded.
  - All four original decision parsers succeeded: `FASTER`, `IDLE`, `IDLE`, `IDLE`, mapped to `(3, 1, 1, 1)`.
  - The test harness stopped before `env.step()` because `env.action_space.contains((3, 1, 1, 1))` was false.
- Error/output: `RuntimeError: Joint action is outside the original action space`.
- Root cause: Harness validation assumed Gym `Discrete(3)` nominal IDs `0..2`. Static inspection showed the original executable longitudinal map is `{4: SLOWER, 1: IDLE, 3: FASTER}`, and original `Run_multi_CAV_LLM.py` passes those IDs directly without the Gym-space gate.
- Proposed fix: Test-harness Compatibility Fix only: preserve the declared-space result as discrepancy evidence, but validate execution against each agent action type's actual `actions` dictionary before following the original `env.step()` path.
- Files affected: Dynamic negotiation prompt in `llm_agent_negotiation_system.py`, Phase 2C harness/artifact, and documentation.
- Semantic impact: Prompt change is the explicitly approved Ollama/Qwen2.5 interface compatibility adaptation. No passing semantics, parser, action map, action space, or simulator logic changed.
- Test result: Negotiation and four decision parser calls passed; environment step count remained `0`. Artifact SHA-256: `FD7838D676A992A087B0D5D8675AC33EBE3A2279BDE5BB549DC5E9B6B9461CC5`.

## Attempt 11

- Date/time: `2026-08-25 10:24:08 +08:00`
- Goal: Correct only the harness validation assumption and complete exactly one original integrated policy step.
- Command: `E:\YiZhen\conda_envs\codriving_repro\python.exe -m scripts.phase2c_integrated_single_step`
- Environment: `intersection-multi-agent-v0`; configured seed field `0`; Ollama `qwen2.5:7b`; endpoint `127.0.0.1:11435`; Memory OFF; no database; no complete episode.
- Expected behavior: Accept only action IDs supported by original executable action dictionaries, then call `env.step()` exactly once.
- Actual behavior:
  - Negotiation raw: `Final Answer: [{"first_vehicle": "MDPVehicle #32", "second_vehicle": "MDPVehicle #968"}]`; parser succeeded; latency about `1.019s`.
  - CAV 0 (`MDPVehicle #32`): `FASTER`, ID `3`, latency about `0.669s`.
  - CAV 1 (`MDPVehicle #968`): `IDLE`, ID `1`, latency about `1.279s`.
  - CAV 2 (`MDPVehicle #168`): `FASTER`, ID `3`, latency about `2.158s`.
  - CAV 3 (`MDPVehicle #176`): `IDLE`, ID `1`, latency about `0.685s`.
  - Joint action `(3, 1, 3, 1)` was false under declared `action_space.contains()` but true for all original executable `ACTIONS_LONGI` maps.
  - Exactly one `env.step((3, 1, 3, 1), env)` succeeded.
  - Result: reward `0.0`, terminal `False`, observation shape `(4, 25)`, info `speed=6.488340192043896`, `cav_crashed=False`, `cost=0.0`, `agents_dones=(False, False, False, False)`.
- Error/output: No runtime error. Declared-space/executable-map inconsistency retained as a warning; no source repair applied.
- Root cause: Attempt 10's blocker was confined to the added harness check, not the original executable pipeline.
- Proposed fix: Applied only to the harness. No further fix required for this single-step reproduction milestone.
- Files affected: `scripts/phase2c_integrated_single_step.py`, retry2 artifact, and documentation. Existing action/simulator source unchanged.
- Semantic impact: No additional research-semantic change. Prompt compatibility adaptation remained exactly within user approval; action execution followed the original repository mapping/path.
- Test result: Success. LLM calls `5` (one negotiation and four decisions), original parser successes `5`, environment steps `1`, complete episodes `0`, Memory retrieval/update `0`. Artifact SHA-256: `54BAFC05526FB297A516C74F98C9CF3291A3CA33AA68D4B0DB3C7869F22F7F94`.

## Attempt 12

- Date/time: `2026-08-25 10:34:38 +08:00`
- Goal: Run the first and only complete `intersection-multi-agent-v0` episode through the verified Ollama pipeline until the original environment terminal condition.
- Command: `E:\YiZhen\conda_envs\codriving_repro\python.exe -m scripts.phase2d_full_episode`
- Environment:
  - Repository HEAD before the attempt: `60cc9a3f4bd9f865aab3964e9b8c6d706b688e0a`
  - Reproduction prefix: `E:\YiZhen\conda_envs\codriving_repro`; Python `3.8.20`
  - Environment ID/scenario: `intersection-multi-agent-v0` / intersection; configured seed field `0`
  - Backend/model/endpoint: Ollama `qwen2.5:7b` at `http://127.0.0.1:11435`
  - Mode: `Local Reproduction / Thesis Mode`; Memory OFF; no database instantiated, retrieval count `0`, update count `0`
  - Episodes requested/executed: `1` / `1`; no rendering or video
- Expected behavior: Reuse the approved centralized negotiation interface adaptation, unchanged parsers, four distributed decisions, original semantic action mapping, and simulator flow until the environment itself returns terminal.
- Actual behavior:
  - The episode completed 43 policy steps, with 43 centralized negotiation calls and 172 per-CAV decision calls.
  - Every negotiation and decision response was saved with its exact messages, raw Ollama API response/content, parsed result, selected semantic action/action ID, and latency.
  - Negotiation parser failures: `0`; decision parser failures: `0`; no fallback or guessed action was used.
  - All 43 joint actions were accepted by the original executable action dictionaries and advanced the simulator.
  - The declared Gym action space returned `False` for 30 of 43 joint actions; all 43 remained executable through the original `{4: SLOWER, 1: IDLE, 3: FASTER}` maps.
  - Cumulative reward was `-2.5`. The final step returned terminal with `cav_crashed=True`, `cost=1.0`, and `agents_dones=[True, True, False, False]`.
  - Terminal reason: `controlled_vehicle_crash`; final controlled crash flags `[True, True, False, False]`; none of the four controlled vehicles had arrived.
  - Episode runtime was `313.4270612s`. Negotiation latency total/mean/min/max was `66.8172500s` / `1.5538895s` / `1.0246777s` / `5.1736241s`. Decision latency total/mean/min/max was `178.4752184s` / `1.0376466s` / `0.3987061s` / `2.3678683s`. Total recorded LLM latency was `245.2924684s`.
- Error/output: No Python runtime crash, transport error, parser error, or compatibility exception. Important warning retained: declared `Tuple(Discrete(3), ...)` does not describe all original executable action IDs. Pre-run GPU state showed GPU 0 idle and GPU 1 carrying desktop/graphics load only; no process was changed or terminated.
- Root cause: The episode's terminal event was the original simulator's controlled-vehicle crash condition, not a program failure. The action-space discrepancy is the already documented repository interface inconsistency and was not repaired.
- Proposed fix: None for this controlled milestone. Do not alter the action space or action mapping based on this single episode. Analyze the recorded trajectory before designing any later experiment.
- Files affected: Added `scripts/phase2d_full_episode.py`, `notes/artifacts/phase2d/full_episode_memory_off.json`, and updated reproduction documentation. No existing LLM, parser, simulator, reward, observation, action-space, scenario, or memory source was changed.
- Semantic impact: None. The runner is experiment instrumentation only and follows the currently approved pipeline. The prior Ollama/Qwen2.5 exact-identifier prompt clarification remains in effect and is not original CoDrivingLLM implementation.
- Test result: Success: exactly one complete episode reached the original terminal condition. Artifact size `1,960,030` bytes; SHA-256 `83C1A91102761159CCA9E26B88572BDD9337C3CE10F386E2BAF12F396B79462D`. No second episode or batch experiment was started.

## Attempt 13

- Date/time: `2026-09-01` (`Asia/Taipei`)
- Goal: Implement the approved Phase 3A Local Memory ON preflight source path without installing dependencies or performing runtime experiments.
- Commands: Read-only Git status/diff inspection; local patch application; Python source compilation using `compile()`; a mocked `urllib` adapter contract test; AST/static invariant checks; `git diff --check`.
- Environment: local analysis workspace `C:\Thesis\CoDrivingLLM-Thesis`; branch `master`; starting HEAD `c3def41b0e629ae1d5d27b52276b3e8c1c6a2336`. No Lab server, Ollama, GPU, simulator step, database, or external network was used.
- Expected behavior: Preserve the original OpenAI embedding path as default/reference; add explicit opt-in Ollama embeddings; keep original Memory query, retrieval, prompt, storage, feedback, and update timing semantics; provide an isolated fail-closed mechanics runner.
- Actual behavior:
  - Added a standard-library `/api/embed` adapter with `embed_query()` and `embed_documents()`, response shape/type/dimension validation, and no fallback.
  - `DrivingMemory` now accepts explicit embedding backend/config and persistence path. The default remains `openai`; `OpenAIEmbeddings` is lazy-imported only for that branch.
  - Added explicit default-OFF `memory_mode`; ON restores `relative_memory()` before the decision and `memory_update()` immediately after it in the original pre-`env.step()` location.
  - Added retrieval trace fields without changing `retrieveMemory()` return data or similarity-search behavior.
  - Added a dedicated Phase 3A runner requiring new absolute database/artifact paths, model digest resolution, one decision/update, count verification, reopen, and second retrieval. The runner contains no `env.step()` call.
  - Removed the source-level placeholder assignment that overwrote `OPENAI_API_KEY`; no credential was added.
- Error/output: Two optional one-line shell checks had quoting-only `SyntaxError` failures before their assertions ran. Corrected simplified checks passed. Source syntax itself passed on every actual source compilation test.
- Root cause: The failed check was caused only by command-string quoting, not source syntax or implementation behavior.
- Files affected: `llm_controller/embedding_backend.py`, `llm_controller/memory.py`, `llm_controller/llm_agent_action.py`, `scripts/phase3a_memory_on_preflight.py`, `notes/reproduction_summary.md`, and `notes/reproduction_log.md`.
- Semantic impact: Ollama embedding is explicitly classified as a `Local Reproduction / Thesis Memory Mode adaptation` because it changes embedding space and potential retrieval ranking. Backend selection, isolated database paths, traces, and the runner are Compatibility/Instrumentation. Original Memory feedback semantics and update timing were not changed.
- Test result: Static implementation checks passed. Runtime status remains untested: no dependency import preflight, embedding request, Chroma creation, LLM decision, persistence test, simulator step, or episode was executed.

### Attempt 13 pre-commit review fixes

- Date/time: `2026-09-06` (`Asia/Taipei`)
- Goal: Apply the four approved Phase 3A pre-commit review fixes without changing Memory research semantics.
- Actual behavior:
  - Added mandatory `--preflight-root`; the target database must be a new strict descendant of that existing root. Repository `db` and `llm_controller/chroma` roots and overlaps are rejected. Database and artifact paths remain absolute/new-only, and the artifact cannot be inside the Chroma directory.
  - Added original parser semantic-action and executable-ID validation before the sole `memory_update()` call. Invalid output stops without update or fallback.
  - Added checkpoint/stage tracking, failed artifact status/type/message, exception re-raise, and `finally` environment close. A Git commit that cannot be resolved now fails closed.
  - Added exact Memory-section extraction/equality, required first/second query and `top_k=2` assertions, and reopened metadata equality against the actual payload passed to `addMemory()`.
- Files affected: `scripts/phase3a_memory_on_preflight.py`, `llm_controller/memory.py`, `notes/reproduction_summary.md`, and `notes/reproduction_log.md` only within the already approved Phase 3A change set.
- Semantic impact: Compatibility/Instrumentation only. Query construction, similarity search, `top_k=2`, stored `page_content`, metadata schema, prompt text, `generate_comment()`, and pre-`env.step()` update timing remain unchanged.
- Test result: Python syntax compilation passed; runner call-count/order/static assertions passed; path-isolation and exact-prompt extraction mocks passed; no-network embedding adapter mock passed; status lifecycle checks passed; and `git diff --check` passed. Two optional one-line assertions initially hit shell quoting-only `SyntaxError`s and were rerun successfully with simplified checks. No package, Ollama, GPU, network, Chroma database, simulator runtime, or episode was used.

## Attempt 14

- Date/time: `2026-09-07` (`Asia/Taipei`)
- Goal: Record the successful Phase 3A Lab server validation and prepare the first controlled full Phase 3B Memory ON episode runner without executing it locally.
- Environment evidence supplied from the Lab server: Python `3.8.20`; `langchain==0.0.335`; `chromadb==0.4.15`; `tokenizers==0.13.3`; `posthog==3.8.4`; Ollama `0.32.9`; chat `qwen2.5:7b`; embedding `nomic-embed-text:latest`; endpoint `http://127.0.0.1:11435`; embedding dimension `768`; `pip check` reported no broken requirements.
- Phase 3A result: fresh count `0`; one decision and original memory update succeeded; count changed `0 -> 1`; reopen count was `1`; retrieval after reopen succeeded; artifact status was `success`.
- Compatibility evidence: `posthog==4.2.0` failed during Chroma initialization on Python 3.8. Pinning `posthog==3.8.4` resolved the failure. `tokenizers==0.13.3` and `posthog==3.8.4` are now recorded as evidence-supported Python 3.8 compatibility pins.
- Proposed Phase 3B command: run `python -m scripts.phase3b_full_episode_memory_on` with an explicit absolute output root, unique run ID, Ollama endpoint, chat model, and embedding model on the Lab server only.
- Expected behavior: reproduce the Phase 2D episode pipeline with Memory as the intended experimental difference: per-CAV top-2 retrieval and exact prompt injection, one original memory update after each valid decision and before the joint environment step, using a fresh isolated database.
- Files affected: `scripts/phase3b_full_episode_memory_on.py`, `notes/reproduction_environment.md`, `notes/reproduction_summary.md`, and `notes/reproduction_log.md`.
- Semantic impact: no new research-semantic change. The local embedding remains the approved `Local Reproduction / Thesis Memory Mode adaptation`; the runner activates the repository-provided Memory flow and adds experiment instrumentation without changing query, top-k, storage, feedback, update timing, simulator, action, reward, observation, scenario, or terminal semantics.
- Test result: Python syntax compilation and AST/source invariants passed; control-flow order confirms semantic/action validation before the original memory update and the update before `env.step()`; `git diff --check` passed. Static checking found and corrected a missing closing parenthesis/indentation defect in the new runner before completion. No package installation, Ollama/GPU/network call, database creation, simulator runtime, or episode was performed during preparation.

## Attempt 15

- Date/time: `2026-09-07` (`Asia/Taipei`)
- Goal: Diagnose Phase 3B server Attempt 1, which stopped during negotiation at policy step `0`, and apply the smallest Ollama/Qwen output-format compatibility clarification.
- Environment/result evidence supplied from the Lab server: negotiation calls `1`; decision, embedding, retrieval, update, and completed policy-step counts all `0`. One real conflict existed between `MDPVehicle #744` and `MDPVehicle #896`.
- Actual behavior: the prompt supplied the correct exact identifiers, but `qwen2.5:7b` returned the JSON object as an escaped quoted string inside the list rather than as a list element object. The unchanged exact-ID negotiation parser therefore returned no pair.
- Root cause: Ollama/Qwen serialization-format drift at the negotiation interface. This occurred before Memory retrieval, embedding, update, or `env.step()` and is not a Memory failure.
- Compatibility fix: `LlmAgent_negotiation_module.send_to_chatgpt()` now explicitly requires every list element to be an actual JSON object, prohibits quoted/escaped JSON strings, and adds dynamically generated Correct/Incorrect serialization examples using the current conflict identifiers. The example order is explicitly marked as format-only and not a passing recommendation.
- Files affected: `llm_controller/llm_agent_negotiation_system.py`, `notes/reproduction_log.md`, and `notes/reproduction_summary.md`. The failed server artifact/database were not modified or deleted.
- Semantic impact: Compatibility Fix only. The Phase 2C exact-identifier rules and original parser remain unchanged. Conflict detection, passing semantics, action mapping, simulator, reward, observation, Memory retrieval/update, and environment configuration are unchanged.
- Test result: syntax compilation passed; dependency-free AST execution of the actual prompt method confirmed dynamic exact-ID Correct/Incorrect examples; the actual unchanged parser method accepted the object-list form and rejected the escaped quoted-string form. Full local runtime was not executed.

## Attempt 16

- Date/time: `2026-09-08` (`Asia/Taipei`)
- Goal: Implement Phase 4C's one-case intersection reproduction runner, fixed seed manifest, and read-only aggregator without launching an integrated LLM case or 20-seed batch.
- Commands: Git/status inspection; Python syntax and CLI checks; manifest assertions; a simulator-only seed reset comparison; and one fixed joint-action simulator transition after the seed check passed.
- Environment: local analysis workspace `C:\Thesis\CoDrivingLLM-Thesis`; HEAD `720e7c9`; existing Python `3.8.20` environment for simulator-only checks. No package installation, Ollama/GPU call, Memory database, LLM request, complete episode, commit, or push.
- Actual behavior: added a fail-closed intersection-only runner with explicit `testing_seeds`, immutable per-case paths, complete initial state/hash and provenance, explicit success evaluation, JSONL trajectory/LLM/Memory evidence, independent-episode Memory ON, and true no-database Memory OFF. Added an artifact-only aggregator that preserves failures and rejects incompatible/incomplete/duplicate inputs. Fixed 20 unique local reproduction seeds before experiment execution. The known declared Gym action-space discrepancy is recorded, while executable validation follows the original per-agent action maps exactly as in Phase 2D/3B.
- Compatibility/instrumentation impact: experiment control and evidence only. The runner reuses the validated Ollama/Qwen prompt/parser/action flow and the Phase 3B Memory sequence. It adds no fallback/retry and does not modify conflict detection, prompts, parser semantics, action mapping, simulator, reward, observation, terminal logic, or Memory retrieval/update semantics.
- Validation result: scripts compiled and CLI help loaded; unsupported scenarios fail closed; manifest shape passed. Seed `104729` reproduced the same snapshot hash across fresh environments, while seed `130363` changed it. One simulator-only `(1, 1, 1, 1)` transition advanced exactly one policy step with reward `0.0` and `done=False`; local `highway_env` was imported. The first attempt was blocked before import by a sandbox-denied Matplotlib cache lock; redirecting that cache to the system temporary directory allowed the same test to pass without repository/environment changes.
- Remaining gate: an integrated Lab-server smoke case is not authorized in this phase. Roundabout/highway/merge blockers and the full 20-seed experiment remain unchanged.

## Attempt 17

- Date/time: `2026-09-09` (`Asia/Taipei`)
- Goal: Repair the first Phase 4C Lab RDP Memory-OFF smoke blocker with the smallest fidelity-preserving argument-plumbing change.
- Run evidence: run ID `phase4c_smoke_off_seed104729`; seed `104729`; initial-state SHA-256 `c482bbb24668d5171f409c574ae66e6821f0d7a214ba161328daaba3352a5851`.
- Actual failure: `TypeError: inference() missing 1 required positional argument: 'env'` occurred in the first policy step while `prompt_engineer()` called the current-lane acceleration safety tool. The failed smoke artifact remains preserved as historical evidence and must not be deleted or overwritten.
- Root cause: original released-code signature/call-site mismatch. `isAccelerationConflictWithCar.inference(self, vid, ego_veh, env)` already required `env` at released commit `f9e71fed`, while `check_safety_in_current_lane()` called it with only `vid` and `ego_veh`. The branch was a previously unexercised latent path, not a Phase 4C, Ollama, or Memory regression.
- Compatibility repair: `llm_controller/prompt_llm.py` now accepts `env` in `check_safety_in_current_lane()` and passes it only to `isAccelerationConflictWithCar.inference()`; `llm_controller/llm_agent_action.py` passes the already available `prompt_engineer()` environment into that helper.
- Files/locations changed: `llm_controller/prompt_llm.py` at `check_safety_in_current_lane()` and its acceleration-tool call; `llm_controller/llm_agent_action.py` at the helper call in `prompt_engineer()`; this log and `notes/reproduction_summary.md` for evidence only.
- Classification: `Compatibility / Runtime Repair`; not a Research-Semantic Change. Current-lane vehicle selection, acceleration/TTC/distance calculation, safety classes, prompts, LLM/parser/action ordering, Memory timing, simulator transition, success evaluation, and Phase 4C artifact semantics were intentionally left unchanged.
- Static verification: textual call-site/signature audit only. No Python project execution, import, simulator, environment reset/step, Ollama, Memory, Chroma, embedding, episode, or experiment was run locally.
- Runtime status: revalidation is pending on the Lab RDP server using a new run ID. Do not reuse `phase4c_smoke_off_seed104729`.

## Attempt 18

- Date/time: `2026-09-09` (`Asia/Taipei`)
- Goal: Freeze the Phase 4D paper-versus-code Memory semantics audit in the reproduction documentation after the matched Phase 4C Lab RDP smoke validation.
- Matched smoke evidence: scenario `intersection`; seed `104729`; Memory OFF and Memory ON recorded the same `initial_state_sha256`; both completed and terminated with a controlled-vehicle crash. The Memory ON case completed `34` policy steps and `136` decisions, retrievals, updates, and successful writes; its fresh database ended at `final_count=136`.
- Interpretation: `34 × 4 = 136` writes follows the activated released-code per-CAV loop. It is not proven to be the paper's exact storage frequency because the paper does not define the unit of an interaction or stored experience.
- IEEE conceptual semantics: Algorithm 1 orders decision, environment transition, impact evaluation, and Memory augmentation. Its text emphasizes negative feedback when an action intensifies danger.
- Released/current semantics: per-CAV retrieval with the final two `prompt_info` lines and `top_k=2`; formatted metadata prompt injection; heuristic feedback from current relation/action; unconditional per-decision append; no failure-only filter; Memory update before `env.step()`.
- Fidelity decision: `INSUFFICIENT EVIDENCE — DO NOT CHANGE YET`. Failure-only storage must not be introduced without separately approved research-semantic reconstruction and a defined post-action evaluator.
- Protocol freeze: Protocol A is Memory OFF; Protocol B is independent-episode Memory ON with a fresh database per case; Protocol C is reconstructed cumulative-interaction Memory ON with a declared ordered sequence and persistent scenario-specific database. Protocol C is conceptually closer to Fig. 7 but is not the exact paper protocol because interaction/seed order, database checkpoints, reset policy, and evaluation-write policy are unpublished.
- Files affected: documentation only — `notes/reproduction_protocol.md`, `notes/reproduction_log.md`, and `notes/reproduction_summary.md`.
- Runtime/semantic impact: none. No runtime code or Memory behavior was modified; no project code, simulator, Ollama, Chroma, embedding, Memory, seed, episode, or experiment was executed.

## Attempt 19

- Date/time: `2026-09-10` (`Asia/Taipei`)
- Goal: Record the completed Phase 4E Lab RDP intersection three-seed mini validation without changing runtime code or experiment semantics.
- Scenario/protocol: `intersection`; seeds `104729`, `130363`, and `155921`; matched Protocol A Memory OFF and Protocol B independent-episode Memory ON.
- Initial-state evidence: OFF/ON hashes matched within every seed: `104729` → `c482bbb24668d5171f409c574ae66e6821f0d7a214ba161328daaba3352a5851`; `130363` → `f3df5aa82c40d5fd21f1a9b8ae2d5b837731470b3c435e57e0b8923d90147215`; `155921` → `e3a580f43600d217d8afd9d119c180ab3671cb65fe1bb30b9afa52a996ca3212`. The three seeds produced distinct hashes.
- Memory OFF results: seeds `104729` and `130363` completed with `success=false` and `controlled_vehicle_crash`; seed `155921` completed with `success=true` and `all_controlled_vehicles_arrived`. Aggregate: `3` cases, `1` success, `2` unsuccessful cases, success rate `0.3333333333333333`; steps mean/median `57`/`41`; simulation time mean/median `11.355555555555554`/`8.2 s`; wall time mean/median `235.54091813333335`/`197.3143661 s`; LLM calls mean/median `285`/`205`.
- Canonical OFF artifact policy: the completed seed-`104729` case is `phase4c_smoke_off_seed104729_retry1`. The original failed smoke artifact remains preserved as historical evidence and was not treated as the canonical completed case. OFF aggregation used an aggregation-only staging directory containing canonical `case.json` artifacts because the smoke/debug root contains both attempts; the staging directory is infrastructure, not experimental data.
- Memory ON results: seed `104729` completed with a controlled-vehicle crash; seeds `130363` and `155921` completed with all controlled vehicles arrived. Aggregate: `3` cases, `2` successes, `1` unsuccessful case, success rate `0.6666666666666666`; steps mean/median `73.33333333333333`/`89`; simulation time mean/median `14.577777777777778`/`17.733333333333334 s`; wall time mean/median `363.7404639`/`452.9575356 s`; LLM calls mean/median `366.6666666666667`/`445`.
- Memory accounting: seed `130363` recorded `388` decisions/retrievals/updates/successful writes and `final_count=388`; seed `155921` recorded `356` for each and `final_count=356`. Every ON case began at count `0`, and final count matched successful writes. All canonical OFF/ON cases recorded zero parser failures and zero fallback actions; OFF Memory activity remained zero.
- Interpretation: mini pipeline/stability validation only. The observed `66.7%` versus `33.3%` must not be interpreted as Memory performance improvement; three seeds are insufficient, and Ollama sampling is not deterministic. No new Memory semantics were introduced, released-code behavior remains preserved, and paper/code differences remain documentation-only.
- Next gate: complete the original GitHub experiment-parameter audit, freeze all parameters, prepare a clean formal output root without smoke/debug retries, and obtain explicit approval before any 20-seed intersection batch.
- Files affected: documentation only — `notes/reproduction_protocol.md`, `notes/reproduction_log.md`, and `notes/reproduction_summary.md`.
- Local activity: documentation editing and textual/Git inspection only. No Python/project code, simulator, Ollama, Chroma, Memory, embedding, seed, episode, or experiment was executed; no commit or push was performed.

## Attempt 20

- Date/time: `2026-09-10` (`Asia/Taipei`)
- Goal: Freeze Phase 4G formal Intersection 20-seed × Memory OFF/ON preparation without launching any case.
- Protocol: exactly the 20 seeds in `notes/phase4_seed_manifest.json`; all OFF cases in manifest order followed by all independent-episode ON cases in the same order; every ON case starts with a fresh isolated database; every matched OFF/ON pair must have identical `initial_state_sha256`; Protocol C is excluded.
- Frozen runtime contract: repository-local simulator, Python `3.8.20`, recorded dependency inventory, complete effective config, original action/reward/termination semantics, Ollama `qwen2.5:7b`, local `nomic-embed-text:latest`, endpoint `127.0.0.1:11435`, resolved model digests, timeout `120 s`, provider-default sampling, strict parsers, no fallback, no automatic retry, Memory `top_k=2`, and update before `env.step()`.
- Formal root: `E:\YiZhen\codriving_formal_runs\intersection`; it must begin without any `case.json` and must not reuse Phase 4C/4E evidence roots. Canonical run IDs and paths are deterministic and immutable.
- Reproduction Infrastructure: added `scripts/phase4g_run_intersection_batch.ps1`, which only sequences the existing one-case runner and stops on the first runtime failure; added `scripts/phase4g_validate_intersection_batch.ps1`, which only reads artifacts and validates exactly 40 canonical cases, exact seeds, required files, completed status, and 20 matched initial-state hashes.
- Failure policy: completed simulator failures remain denominator cases; runtime/infrastructure failures remain preserved, stop the batch, receive no automatic retry, and cannot be replaced by another seed.
- Semantic impact: none. No simulator, prompt, parser, action, Memory, success, termination, reward, or aggregation semantics were changed. All known non-blocking paper/code discrepancies remain documentation-only.
- Local verification: textual/static diff and PowerShell source inspection only. No project Python, environment, simulator, reset/step, Ollama, embedding, Chroma, Memory, seed, episode, batch, commit, or push was executed.
- Execution status: preparation only. Formal RDP execution still requires the documented mandatory gate and explicit approval.

## Attempt 21

- Date/time: `2026-09-10` (`Asia/Taipei`)
- Goal: Record the completed Phase 4G formal Intersection result as Phase 4H documentation; perform a separate read-only Phase 5A Merge source audit without implementing or executing Merge.
- Formal provenance: Git `2c8e01d7011d5caab5dac215b5c1a81a674d2114`; Python `3.8.20`; Ollama `0.32.9`; chat `qwen2.5:7b` digest `845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e`; embedding `nomic-embed-text:latest` digest `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
- Completeness: all 20 frozen seeds completed in both modes; validator `status=complete`; 20 OFF, 20 ON, and `20/20` matched initial-state pairs.
- Memory OFF result: `7/20` successes, `13` completed unsuccessful controlled-vehicle crashes, observed success rate `0.35`; mean/median steps `61.3/45.5`; simulation time `12.2/9.066666666666666 s`; wall time `257.276676745/228.82761075 s`; LLM calls `306.5/227.5`.
- Memory ON result: `6/20` successes, `14` completed unsuccessful controlled-vehicle crashes, observed success rate `0.30`; mean/median steps `54.5/41.0`; simulation time `10.826666666666666/8.166666666666666 s`; wall time `294.988538925/253.5811094 s`; LLM calls `272.5/205.0`.
- Pair transitions: success→success `3`, failure→failure `9`, success→failure `4`, failure→success `4` (OFF→ON).
- Interpretation: descriptive local-reproduction evidence only. Do not infer a positive or negative Memory effect: Qwen/Ollama generation used provider-default sampling without frozen `temperature`, `top_p`, or LLM seed, and the local models differ from the paper's OpenAI path.
- Artifact policy: Phase 4 structured JSON/JSONL plus case-local Chroma artifacts preserve the numerical/provenance evidence required for analysis; original MP4/XLSX outputs are not required for this formal result.
- Non-fatal warning: formal cases could emit `RuntimeWarning: divide by zero encountered in scalar divide` from `prompt_llm.py` at `ttc = distance / relativeSpeed` and still complete. Classified as an observed non-fatal released/current runtime warning; no repair was made.
- Semantic impact: none. No formal seed was rerun or replaced; all known released-code discrepancies remain unchanged.
- Local activity: documentation editing and static Merge/Git inspection only. No Python project execution, environment instantiation/reset/step, simulator, Ollama, embedding, Chroma, Memory, seed, episode, or batch was run; no commit or push was performed.
