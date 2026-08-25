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
