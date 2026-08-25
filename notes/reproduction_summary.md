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
