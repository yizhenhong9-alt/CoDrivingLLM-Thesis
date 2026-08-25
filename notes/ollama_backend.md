# Ollama Backend Contract Analysis

## Scope and mode

- Phase: `Phase 2B — Ollama Backend Adaptation & LLM Smoke Test`
- Required label: `Local Reproduction / Thesis Mode`
- This mode is not an exact numerical reproduction of OpenAI `gpt-4o-mini`.
- Current status: minimal adapter implemented and both required single-call smoke tests passed.

## Original centralized negotiation contract

- File/class: `llm_controller/llm_agent_negotiation_system.py`, `LlmAgent_negotiation_module`
- Caller: `llm_controller_run(env)` runs `detect_conflicts(env)`, then calls `send_to_chatgpt(env, conflict)`.
- Prompt construction: `send_to_chatgpt()` recomputes conflicts, builds `conflicting_vehicles_info`, formats vehicle IDs, speeds, and distances into one prompt, and requests a `"decisions"` list of `first_vehicle`/`second_vehicle` pairs.
- Message structure: one OpenAI chat message with role `system` and the entire prompt as `content`; there is no separate user message.
- OpenAI transport: hard-coded proxy `http://127.0.0.1:7890`, placeholder source-level API key, base URL `https://api.openai.com/v1`, `OpenAI(...).chat.completions.create()`.
- Model/parameters: hard-coded `gpt-4o-mini`; no explicit temperature, seed, top-p, token limit, timeout, or streaming option.
- Raw text extraction: `completion.choices[0].message.content` becomes `negotiation_content`.
- Return contract: `(negotiation_content, conflicting_vehicles_info)`.
- Downstream parser location: `LlmAgent_action_module.transfer_negotiation_prompts_to_results()` calls `extract_vehicle_conflicts(negotiation_prompt, ego_vehicle_id)`.
- Negotiation parser: regex requires exact quoted fields, exact field order, one literal space after each colon, and vehicle strings matching `MDPVehicle #[0-9]+` or `IDMVehicle #[0-9]+`. It returns `(first, second, 'first'|'second')` entries involving the ego vehicle.

Mapping:

```text
OpenAI chat completion
-> completion.choices[0].message.content
-> negotiation_content (raw str)
-> LlmAgent_action_module.extract_vehicle_conflicts()
-> list[(first_vehicle, second_vehicle, ego_order)]
-> transfer_negotiation_prompts_to_results()
-> per-CAV negotiation advice text
```

## Original distributed per-CAV decision contract

- File/class: `llm_controller/llm_agent_action.py`, `LlmAgent_action_module`
- Caller: `llm_controller_run()` iterates each controlled CAV, derives negotiation advice and deterministic scenario/safety information, then calls `send_to_chatgpt()` once per CAV.
- Prompt construction: `send_to_chatgpt()` concatenates the original `PRE_DEF_PROMPT` prefix, current scenario, traffic rules, decision cautions, empty `past_memory`, centralized negotiation advice, and exact final-output instructions.
- Message structure: one OpenAI chat message with role `system` and the entire prompt as `content`; there is no separate user message.
- OpenAI transport: same hard-coded proxy, placeholder API key, base URL, and chat-completions client pattern as negotiation.
- Model/parameters: hard-coded `gpt-4o-mini`; provider defaults are used for sampling, timeout, token limit, and streaming.
- Raw text extraction: `completion.choices[0].message.content` becomes `decision_content`.
- Decision parser: `extract_decision()` searches for the literal substring `"decision": {`, takes text through the next `}`, then recognizes allowed action substrings. Intersection/merge recognizes `FASTER`, `SLOWER`, or `IDLE`; highway also recognizes lane changes.
- Action mapping: `get_action_id_from_name()` maps the parsed semantic action through the scenario-specific `ACTIONS_ALL`; unknown values map to `-1` in the original code.
- Return contract: `numpy.array([action_id])`.

Mapping:

```text
OpenAI chat completion
-> completion.choices[0].message.content
-> decision_content (raw str)
-> extract_decision()
-> semantic action string
-> get_action_id_from_name()
-> numeric action ID
-> numpy.array([action_id])
```

## Required invariants for a future Ollama adapter

- Preserve both centralized and per-CAV call boundaries.
- Preserve every original prompt string and the single-system-message structure for the first compatibility test.
- Preserve raw-text parser inputs and action mapping.
- Keep OpenAI transport available; do not replace it with Ollama-only code.
- Keep proxy/API-key handling isolated to the OpenAI branch.
- Do not import OpenAI in Ollama-only execution when the `openai` package is intentionally absent.
- Do not add parser fallback, default `IDLE`, guessed passing order, or prompt rewrites.
- Keep memory retrieval/update disabled and avoid importing memory dependencies.

## Implemented minimal transport design

- `llm_controller/llm_backend.py` adds a small backend module using Python standard-library HTTP/JSON support; no new package was necessary.
- Explicit constructor configuration contains backend, endpoint, exact model, timeout, and streaming mode.
- The OpenAI branch preserves the existing model/client request and response extraction and is lazy-imported only when selected.
- The Ollama branch POSTs the same `messages` list to `/api/chat`, with `stream: false`, and passes only `response['message']['content']` to the existing parsers.
- Do not set temperature, seed, top-p, or `num_predict` until the selected model and provider-default difference are explicitly documented. The original OpenAI code sets none of these.
- Save exact messages, raw response, parsed value, request configuration, and latency for each single-call smoke test.

## Selected Ollama configuration and results

- Executable: `C:\Users\yizhen0925\AppData\Local\Programs\Ollama\ollama.exe`
- Version: `0.32.9`
- Session-local endpoint: `http://127.0.0.1:11435`
- Model storage: `E:\YiZhen\ollama_models`; applied only to the launched child process.
- Visible models: `qwen2.5:7b`, `llama3:latest`, `nomic-embed-text:latest`.
- Selected model: `qwen2.5:7b` (7.6B, `Q4_K_M`).
- Timeout: `120s`.
- Streaming: off.
- Sampling controls: none explicitly supplied; Ollama provider defaults were retained and documented rather than tuned.
- Negotiation result: latency about `35.537s`; raw response used Markdown plus extra prose; original regex parser succeeded.
- Decision result: latency about `0.761s`; raw response used explanatory prose plus `"decision": {"IDLE"}`; original parser returned `IDLE`, mapped to ID `1`.
- Full artifacts: `notes/artifacts/phase2b/centralized_negotiation.json` and `notes/artifacts/phase2b/per_cav_decision.json`.

## Phase 2C observed output variance

- A later real-state integrated attempt produced `{"first_vehicle": "i", "second_vehicle": "j"}` instead of actual simulator vehicle IDs, even though the conflict description contained those IDs.
- The original negotiation regex correctly returned no match; no guessing or fallback was introduced.
- This demonstrates that the Phase 2B parser success does not guarantee output-format stability across provider-default Ollama calls.
- Artifact: `notes/artifacts/phase2c/integrated_single_step.json`.
- Any prompt clarification or parser mapping requires explicit approval before Phase 2C is retried.

## Approved Qwen2.5 negotiation interface clarification

- Classification: Ollama/Qwen2.5 interface compatibility adaptation; it is not original CoDrivingLLM implementation.
- The prompt now derives the allowed exact vehicle identifiers from each current conflict at runtime.
- Generic identifiers (`i`, `j`, `vehicle_i`, `vehicle_j`) and placeholders are explicitly prohibited in output.
- Both exact-ID orderings are shown for each pair as neutral formatting alternatives, so the model still decides passing priority from the unchanged safety task.
- The original negotiation regex parser was not modified.
- Phase 2C retry confirmed actual-ID output and parser success, followed by four decision parser successes and one environment transition.
