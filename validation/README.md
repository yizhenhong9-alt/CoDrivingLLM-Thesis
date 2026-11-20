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
local highway_env was loaded. KinematicsObservation now uses public `pd.concat`
for nearby-vehicle rows and zero-padding rows, preserving their order and
`ignore_index=True`. No package upgrade or simulator policy change is required
for this fix. Actual successful execution still needs a new RDP report.

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
cover 0--4 neighbours and zero padding. Live comparisons use the current
observation method body and a copy with just the two concat expressions
replaced by append. Both expose the intermediate DataFrame for comparison;
neither replaces the installed observation method or changes simulator policy.
Frames (values, columns, order, index, dtype) and returned NumPy arrays must
match exactly. Default expected counts: 5 synthetic cases and 48 live cases
(3 seeds x 4 checkpoints x 4 CAVs), status passed and exit code 0.
Return full console, Git status and the unique JSON report, even on failure.
Passing these cases does not prove equivalence for every pandas version or
arbitrary DataFrame input, nor driving decision safety.

## Planned separation

Model-specific modules such as `qwen3_agent_negotiation_system.py` can coexist
with the original GPT modules. Share model-independent validation/parsing where
appropriate rather than copying every helper. A later experiment CLI can select
model, scene, memory, seed, steps and output formats. Unsupported memory-on must
raise a clear error until local embeddings and a compatible vector store are
implemented.
