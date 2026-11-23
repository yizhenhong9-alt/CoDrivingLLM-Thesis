# Incremental validation

Keep verification scripts here. The author's `Run_multi_CAV_LLM.py` and
controller modules remain unchanged in this first validation step.

## Environment-only smoke test

Run in the laboratory RDP's Windows PowerShell, from the repository root,
using a confirmed simulator environment (not conda base or the WSL vLLM venv).
The Qwen server can remain stopped.

```powershell
python validation/smoke_intersection.py --help
python validation/smoke_intersection.py --seed 0 --max-steps 1 --action IDLE --output-dir 'E:\YiZhen\qwen-tests\phase4\environment-smoke'
```

Current options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--seed` | `0` | Explicit `testing_seeds` passed to the author's reset |
| `--max-steps` | `1` | Maximum decision steps in one episode |
| `--action` | `IDLE` | Same fixed action for all CAVs; also FASTER or SLOWER |
| `--output-dir` | `results/intersection-smoke` | One uniquely named JSON per invocation |

This script only supports intersection and does not import LLM/memory modules.
It never writes XLSX or MP4. Scene selection, memory on, and XLSX/MP4 switches
are not implemented yet; do not pass hypothetical flags for them.

The test deliberately uses the execution action mapping, not `Discrete(3)`
sampling/contains. It does not apply the LLM action module's speed clamp.
Consequently it validates the environment, not the full driving algorithm or
decision safety. The original controller, routes, rewards and physics remain
unchanged.

### First RDP failure and compatibility fix

At commit `54116f2`, Python 3.8.20 / Gym 0.15.3 / NumPy 1.24.4 /
pandas 1.3.5 failed during the constructor's reset, before any decision step:
`DataFrame` has no attribute `_append`. The report confirmed that the repository's
local highway_env was loaded. Commit `45c83d9` used public `pd.concat` for
nearby-vehicle and zero-padding rows; the RDP one-step test passed with exit 0,
three physics ticks and 0.2 simulated seconds. At `fcaecdf`, all five synthetic
and 48 live append/concat comparisons passed under pandas 1.3.5.

Following the user's minimal-change preference, production now uses public
`DataFrame.append` at both sites, preserving row order and `ignore_index=True`.
This requires an append-compatible pandas version (the confirmed one is 1.3.5).
It does not establish that the original `_append` was a typo. No packages,
traffic rules or controllers were changed. Run the one-step smoke again after
pulling this revision; its production append path still needs RDP confirmation.

## Report and acceptance

Return the complete console, exit code and the JSON path printed as `Result:`.
Attach that JSON, including failed reports, for inspection.

For the first run expect exit code 0, `status=completed`, one entry in `steps`,
four initial controlled vehicles and four actions `[1, 1, 1, 1]`. Normally
`stop_reason=max_steps`, three physics ticks and 0.2 simulated seconds are
expected. An early environment termination must be reviewed, not silently
counted as a normal full step. Inspect `environment_source` to confirm the
repository's highway_env was imported.

JSON includes seed, Python executable, versions, commit, scene config, route,
vehicle speed/target speed/index, low-level steering (radians), acceleration,
reward and termination info. A recorded commit identifies HEAD, not uncommitted
edits: always return `git status --short --branch` alongside results.

Only after review, repeat the same seed to compare initial states (excluding
wall time and timestamps), then increase to 3--5 steps. LLM/negotiation and
memory-on validation are later steps. Never run the author's main script merely
to check dependencies, and do not install all requirements into a shared base.

## Append/concat equivalence (pandas 1.3.5)

```powershell
python validation/check_observation_concat.py --seeds 0 1 42 --max-steps 3 --output-dir 'E:\YiZhen\qwen-tests\phase4\concat-equivalence'
Write-Output "test_exit=$LASTEXITCODE"
```

Requires the confirmed codriving_repro environment, without package changes.
The baseline is the hypothesis that public `DataFrame.append` was intended;
it is not an execution of the unavailable `_append`. Five synthetic cases
cover 0--4 neighbours and zero padding. Live comparisons derive explicit concat
and append variants from the current observation body, replacing only the two
merge expressions. Either production implementation is supported, and its method
is recorded in the report. Both expose the intermediate DataFrame for comparison;
neither replaces the installed observation method or changes simulator policy.
Frames (values, columns, order, index, dtype) and returned NumPy arrays must
match exactly. Default expected counts: 5 synthetic cases and 48 live cases
(3 seeds x 4 checkpoints x 4 CAVs), status passed and exit code 0.
Return full console, Git status and the unique JSON report, even on failure.
Passing these cases does not prove equivalence for every pandas version or
arbitrary DataFrame input, nor driving decision safety.

## Offline original prompt capture

```powershell
python validation/capture_intersection_prompts.py --seed 0 --output-dir 'E:\YiZhen\qwen-tests\phase4\prompt-capture'
Write-Output "capture_exit=$LASTEXITCODE"
```

Use the confirmed Windows codriving_repro environment. Leave Qwen stopped.
The original negotiation/action classes build their prompts with SDK calls
intercepted by record-only replacements. HTTP client construction is replaced,
and socket connections are blocked during the agent calls. No key or endpoint
is used. Original production modules are unchanged.
OpenAI/httpx imports are supplied by process-local stub modules: installing
those packages is not required for offline capture. This does not validate
real SDK connectivity. The first capture attempt failed at import httpx before
capturing any calls; the tool was corrected without changing conda packages.

An arbitrary negotiation fixture orders each detected mutual conflict pair by
simulation ID. Action prompts thus contain real scene data but a test passing
order, not actual LLM output or a safety claim. Fixed IDLE responses exercise
the original parser, but are never applied: env.step is not called. The original
action builder's speed clamp does execute; before/after states are recorded.
DrivingMemory is not imported/constructed. This is validation-only memory off,
not a completed production memory switch or model replacement.

Expected: status captured, five captured calls (one negotiation plus four action),
environment_steps=0, memory_module_imported=false and exit code 0. Return the
whole JSON and console, including failures. The report preserves original raw
vehicle labels alongside simulation IDs: original labels use object identity
and can vary across processes. Token lengths still need the Qwen tokenizer.

## Safety helper parameter regression

```powershell
python validation/check_safety_dispatch.py
Write-Output "dispatch_exit=$LASTEXITCODE"
```

Expected: five tests, OK, exit code 0. Uses the actual helper body with strict
tool doubles and checks the action caller AST; needs only the standard library.
It verifies argument dispatch, not the correctness of safety formulas.

At `3e7bf3a`, offline capture recorded negotiation but failed before the first
action prompt: acceleration inference requires env, while its caller omitted it.
Commit `0055640` initially forwarded env through the caller chain. Subsequent
review found no env use in the tool body; author commit `c88cdb69` introduced
the parameter without using it. With user agreement, remove the unused tool
parameter and restore the original helper/caller arguments. Safety formulas
remain unchanged; this does not bypass the check or prove the author's intent.
Other safety branches and other scenes still need separate runtime validation.

## Strict output schema (Qwen preparation)

### Spark offline validation (M06)

After syncing the reviewed Git commit, use the existing simulation interpreter:

```bash
cd /home/nclab/Yizhen/src/CoDrivingLLM-Thesis
PYTHONDONTWRITEBYTECODE=1 /home/nclab/Yizhen/envs/codriving-sim-py38/bin/python validation/validate_spark_offline.py --output-dir /home/nclab/Yizhen/runs/M06-offline
```

This runs 38 unit tests (37 before M07) followed by strict/legacy fixtures. It starts no model,
makes no model requests and applies no fixture actions. Child caches/temp files
stay below the output directory; CUDA devices are hidden for these children and
BLAS/OpenMP threads limited to one. CPU/RAM/disk remain shared hardware.
Check result.json plus command logs; any failure stops subsequent commands.
Do not install packages or change shared settings to work around a failure.
For the M07 relative-source-path failure after all four suites passed, add
`--resume-fixtures` to run only its new path regression and the two fixtures.

Modification reports: [index](../modification_reports/README.md).
M10: [real-response session report](../modification_reports/M10-real-response-session/report.md).
Unlike offline tools, `run_qwen_live_session.py` DOES launch the specified model
on Spark, uses the existing simulation interpreter for live replies without
env.step, then signals only its own API parent for shutdown. Rechecks current
resources and port before launch; no group kill or automatic SIGKILL fallback.
Read the report before running; this has not yet been validated on Spark.
M09: [runtime/preflight report](../modification_reports/M09-live-preflight/report.md).
`inspect_qwen_runtime.py --output-dir /home/nclab/Yizhen/runs/M09-preflight`
collects resource snapshots, installed source excerpts and existing Step8J-R1
metadata using the inference interpreter. It does not import vLLM/torch, launch
models, send signals or make API requests. A collected snapshot is not a resource
reservation or proof that shutdown is fixed.
M08: [token-count report and interpreter explanation](../modification_reports/M08-prompt-token-budget/report.md).
Run tokenizer counting with the Spark inference Python 3.12, not simulation
Python 3.8. The tool uses existing local tokenizer files, no model weights or
network. `check_prompt_tokens.py` tests the counting logic with a fake tokenizer.
M05: `python validation/check_qwen_single_step.py` runs fake-environment offline
flow tests. The [M05 report](../modification_reports/M05-qwen-single-step/report.md)
documents the new single-step CLI, its local missing-gym failure and pending
Spark fixture checks. This is not a completed real-model integration result.
M04: run `python validation/check_memory_off.py` for offline entry assignment and
action-builder checks. See the [M04 report](../modification_reports/M04-memory-off/report.md)
for test-double boundaries. Do not run the full legacy entry for this check: it
still invokes the original cloud agents and multi-episode simulation.
M02 adds explicit `scene="intersection"`, `scene="merge"` or `scene="highway"`
to `parse_action`; no scene is guessed. Run
`python validation/check_vehicle_actions.py` for scene and vehicle batch checks.
These utilities are not yet connected to the simulator entry point.

### Original parser reproduction

Run `python validation/reproduce_original_parsers.py` to execute the two actual
method bodies from the original action agent using AST extraction. No agent
constructor, SDK, model, memory or simulator is loaded. The nine tests describe
observed original behavior: a passing reproduction includes known defects and
does not mean the original parser is correct. JSON output includes the source
SHA256, interpreter version, inputs and actual results. Results from Windows
Python 3.13 are stored in [original_parser_reproduction.json](./original_parser_reproduction.json).
The initial exploratory assertion for plain JSON IDLE was incorrect; execution
showed it returns IDLE successfully, and the final test preserves that result.
No Spark Python 3.8 or real model response validation is claimed.

### New parser checks

Run `python validation/check_output_schema.py` (standard library only).
The parser in [output_schema.py](../llm_controller/output_schema.py) accepts:

- Action: `{"vehicle_id":3,"decision":"IDLE"}`. The caller supplies the current
  vehicle ID and available action names. Mapping remains IDLE=1, FASTER=3,
  SLOWER=4. Names must match exactly.
- Negotiation: `{"decisions":[{"first_vehicle":3,"second_vehicle":4}]}`.
  Each input conflict pair must occur exactly once; no conflicts means `[]`.

Only a complete JSON object is accepted, without Markdown fences or prose.
Invalid replies raise `OutputValidationError`; no fallback action is selected.
The caller must retain the raw reply and stop before env.step on failure.
IDs must come from the current episode mapping, not `id(vehicle) % 1000`.
This validates format and pair coverage, not safety or ordering cycles.
The new parser is not yet connected to the original agents: their old prompts
and parsing remain the baseline until a separate Qwen integration step.
No model, memory, simulator, or safety policy is changed by this addition.

## Planned agent integration

Model-specific modules such as `qwen3_agent_negotiation_system.py` can coexist
with the original GPT modules. Share model-independent validation/parsing where
appropriate rather than copying every helper. A later experiment CLI can select
model, scene, memory, seed, steps and output formats. Unsupported memory-on must
raise a clear error until local embeddings and a compatible vector store are
implemented.
