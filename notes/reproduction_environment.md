# CoDrivingLLM Reproduction Environment

## Repository baseline

- Recorded at: `2026-08-24 17:45:47 +08:00` (`Asia/Taipei`)
- Working directory: `E:\YiZhen\Thesis\CoDrivingLLM-Reproduction`
- Branch: `master`
- HEAD: `f9e71fed08c1772cf4009ed61dfe91177019cf7d`
- Remote: `origin https://github.com/FanGShiYuu/CoDrivingLLM.git`
- OS runtime: `Microsoft Windows NT 10.0.22631.0`
- Conda: `26.3.2`

## Environment design

- Intended name: `codriving_repro`
- Active prefix: `E:\YiZhen\conda_envs\codriving_repro`
- Proposed Python: `3.8.20`
- Proposed pip: `24.2`
- Channel used for isolated provisioning: `conda-forge` through per-command `--override-channels`; global Conda configuration was not changed.
- Python 3.8 was selected from repository pins and the historical environment evidence. The historical `codriving_yizhen` environment uses Python `3.8.20` with `gym==0.15.3`, `pandas==1.3.5`, `openai==1.2.2`, `langchain==0.0.335`, and `chromadb==0.4.15`.
- The historical environment was inspected read-only and was not cloned or modified.

## Current status

- `codriving_repro` was successfully created at `E:\YiZhen\conda_envs\codriving_repro` using an explicit prefix.
- Verified interpreter: `E:\YiZhen\conda_envs\codriving_repro\python.exe`
- Verified Python: `3.8.20`
- Verified pip: `24.2` from `E:\YiZhen\conda_envs\codriving_repro\lib\site-packages\pip`
- A temporary environment created at `C:\Users\yizhen0925\.conda\envs\codriving_repro` was removed after confirming it contained only the initial Python/pip runtime and had not been used.
- The unusable `E:\YiZhen\miniconda3\envs` location was abandoned without changing its ACL or requesting Administrator privileges.
- Installed Phase 2A simulator pins: `gym==0.15.3`, `numpy==1.24.4`, `pandas==1.3.5`, `pygame==2.6.1`, and `matplotlib==3.7.5`.
- `pip check` result: `No broken requirements found.`
- Important transitive versions include `scipy==1.10.1`, `pyglet==1.3.2`, and `cloudpickle==1.2.2`. Unpinned `pytz` resolved to `2026.3.post1`, which differs from the historical environment's `2026.2`; no incompatibility has yet been demonstrated.
- Confirmed absent: `openai`, `langchain`, `chromadb`, and `ollama`.
- Confirmed local simulator import: `E:\YiZhen\Thesis\CoDrivingLLM-Reproduction\highway_env\__init__.py`.
- Gym registration confirmed: `intersection-multi-agent-v0`, `merge-multi-agent-v0`, and `highway-v0`.
- The pandas API mismatch documented in Attempt 5 was repaired by the approved one-line Compatibility Fix in `highway_env/envs/common/observation.py` (`DataFrame._append()` to `DataFrame.append()`).
- `intersection-multi-agent-v0` now passes `gym.make()`, explicit `reset()`, and one simulator-only joint-action step.

## Deferred Stage 1–3 package set

No packages below have been installed yet. The planned minimal exact-version set is:

- `gym==0.15.3`
- `numpy==1.24.4`
- `pandas==1.3.5`
- `pygame==2.6.1`
- `matplotlib==3.7.5`

The PyPI `highway-env` package, LLM packages, memory packages, and Ollama-related packages are intentionally excluded from the Phase 2A minimum until later evidence requires them.

## Phase 2B Ollama inventory

- Recorded at: `2026-08-25 09:50:29 +08:00` (`Asia/Taipei`)
- Execution mode label: `Local Reproduction / Thesis Mode` (not an exact GPT-4o-mini reproduction)
- Ollama executable: `C:\Users\yizhen0925\AppData\Local\Programs\Ollama\ollama.exe`
- Ollama client/service version: `0.32.9`
- Local endpoint: `http://127.0.0.1:11434`
- Health evidence: `GET /api/version` returned `{"version":"0.32.9"}` and `GET /api/tags` returned an empty `models` array.
- Available models: none.
- Selected model: none; selection and inference are blocked until the user prepares or explicitly selects an existing local model.
- GPU state: not queried because no model is available and no inference may proceed. `nvidia-smi` remains mandatory immediately before the first future inference.
- Additional Python packages: none installed for Phase 2B. The standard library is sufficient for a minimal localhost JSON HTTP transport design.
- Backend implementation status: not started because there is no model with which to validate transport or parser compatibility.

### Selected session-local Ollama service

- Recorded at: `2026-08-25 10:05:41 +08:00`
- Model storage: `E:\YiZhen\ollama_models`
- Configuration scope: environment inherited only by a separately launched current-user child process; no User/Machine persistent environment variable was changed.
- Endpoint: `http://127.0.0.1:11435`
- Service process at launch: PID `45296`
- Selected generation model: `qwen2.5:7b`, 7.6B parameters, `Q4_K_M`, digest prefix `845dbda0ea48`, stored size about 4.7 GB.
- Other visible models: `llama3:latest` and `nomic-embed-text:latest`.
- Request contract: POST `/api/chat`, one unchanged system message, `stream=false`, timeout `120s`, no explicit sampling controls.
- Additional Python dependencies: none; transport uses Python standard-library `urllib` and `json`.
- Pre-inference GPU state: two RTX 4090 GPUs. GPU 0 was idle (`0 MiB`, `0%`); GPU 1 had about `2434 MiB`, `9%`, with desktop/graphics processes only.
- Post-smoke state: Ollama loaded `qwen2.5:7b` on GPU 0 only, reported about `6.6 GB` and `100% GPU` processor placement; GPU utilization was idle after requests completed.
