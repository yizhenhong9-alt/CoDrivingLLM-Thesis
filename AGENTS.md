# CoDrivingLLM Controlled Reproduction Instructions

## 1. Project Goal

This repository is the controlled reproduction workspace for the original CoDrivingLLM paper:

**Towards Interactive and Learnable Cooperative Driving Automation: a Large Language Model-Driven Decision-Making Framework**

The current objective is to establish a reproducible and explainable baseline before any thesis extension is implemented.

This repository is NOT currently for:

* thesis novelty implementation
* architecture redesign
* unrelated LLM methods
* Actor–Reasoner integration
* V2X communication/resource modeling
* Adaptive Message Generation
* arbitrary performance optimization

The priority is faithful reproduction and understanding.

---

## 2. Workspace Role

Current reproduction workspace:

`E:\YiZhen\Thesis\CoDrivingLLM-Reproduction`

Original analysis/reference workspace:

`E:\YiZhen\Thesis\CoDrivingLLM-Thesis`

Do not modify files in the original analysis/reference workspace unless the user explicitly requests it.

The reproduction repository begins from a fresh clone of the official CoDrivingLLM repository.

---

## 3. Language

All user-facing explanations, plans, error analyses, modification summaries, and experiment reports must be written primarily in Traditional Chinese (繁體中文).

Keep the following in English:

* paper titles
* technical terms
* model names
* algorithm names
* class names
* function names
* variable names
* filenames
* file paths
* commands
* terminal output
* error messages

Example:

「目前 `LlmAgent_action_module.send_to_chatgpt()` 會建立 per-CAV prompt，接著呼叫 `gpt-4o-mini`。」

Do not unnecessarily translate identifiers.

---

## 4. Research Reference

The Phase 1 paper–code analysis is available at:

`notes/reference/paper_code_mapping.md`

Treat this file as a reference document.

Do not overwrite or reinterpret its findings without new evidence.

When reproduction produces evidence that contradicts the Phase 1 analysis:

1. record the new evidence;
2. explain the discrepancy;
3. do not silently replace the original conclusion.

---

## 5. Reproduction Principle

The goal is NOT merely:

> Make the program run.

The goal is:

> Reproduce the original CoDrivingLLM behavior with the smallest necessary and fully documented compatibility changes.

Priority order:

1. Research semantics preservation
2. Reproducibility
3. Original repository behavior
4. Minimal compatibility repair
5. Experiment traceability
6. Convenience

Never sacrifice research semantics merely to avoid an error.

---

## 6. Original Behavior vs Compatibility Fix

Every proposed modification must first be classified as one of:

### A. Compatibility Fix

Examples:

* obsolete API syntax
* Windows path issue
* dependency-version incompatibility
* missing output directory
* deprecated library invocation
* optional proxy configuration
* safe secret/config loading
* parser failure caused strictly by API format drift

Compatibility fixes may be implemented only after explaining:

* root cause
* affected file/function
* proposed change
* why research semantics are preserved
* how the change will be tested

### B. Research-Semantic Change

Examples:

* reward function
* observation design
* action space
* scenario definition
* vehicle behavior
* LLM reasoning logic
* prompt meaning
* memory algorithm
* conflict detection semantics
* safety logic
* evaluation metrics
* seed protocol
* traffic density
* number of vehicles

Do NOT implement a research-semantic change without explicit user approval.

If uncertain whether a change is A or B, treat it as B.

---

## 7. Memory OFF and Memory ON

Memory is an intentional experimental variable in CoDrivingLLM.

Do NOT treat the default commented memory calls as automatically being a repository defect.

Define two explicit experimental modes:

### Memory OFF

The default execution path where:

* memory retrieval is not injected into the prompt
* memory augmentation/update is disabled

### Memory ON

The intended CoDrivingLLM learning condition where the existing:

* retrieval
* few-shot memory injection
* memory augmentation/update

mechanisms are explicitly enabled.

The reproduction workflow should first establish a stable baseline, then compare Memory OFF and Memory ON under matched conditions.

For future thesis work, Memory ON is expected to be the primary CoDrivingLLM baseline unless the user specifies otherwise.

When running either mode, always record:

* mode: Memory OFF / Memory ON
* database path
* initial database state
* number of stored experiences if available
* retrieval count / shots
* scenario
* seed
* model
* experiment date

Do not mix results from Memory OFF and Memory ON.

---

## 8. Memory Semantics Must Still Be Verified

Although the implementation components exist, do not assume that simply uncommenting memory calls perfectly reproduces the paper.

Before declaring Memory ON reproduction successful, verify:

* when retrieval occurs
* what query is used
* how many memories are retrieved
* what data are injected into the prompt
* when memory update occurs
* what experience is stored
* whether feedback represents the previous action outcome as described by the paper
* whether database state persists across episodes/runs

If paper semantics and repository behavior differ, document the difference instead of inventing a new evaluator.

---

## 9. Conda Environments

Historical environment:

`codriving_yizhen`

Location:

`E:\YiZhen\miniconda3\envs\codriving_yizhen`

This is a historical working/reference environment.

Do not:

* install into it
* uninstall from it
* upgrade it
* downgrade it
* repair it
* modify its package set

unless explicitly authorized.

A separate reproduction environment should be used:

`codriving_repro`

The reproduction environment must be created specifically for this repository.

Before creating or changing it:

1. inspect repository requirements;
2. inspect the historical environment for reference;
3. choose a compatible Python version;
4. record the environment design in documentation.

Do not blindly install the newest package versions.

---

## 10. Dependency Safety

Do not use broad upgrade commands such as:

* `pip install -U ...`
* `pip install --upgrade ...`
* `conda update --all`

without explicit approval.

Prefer exact or evidence-supported versions.

The original repository uses an old software stack and custom/local `highway_env`.

Pay particular attention to:

* Python
* `gym`
* local `highway_env`
* PyPI `highway-env`
* `openai`
* `httpx`
* `langchain`
* `chromadb`
* `numpy`
* `pandas`
* `pygame`
* `imageio`
* `imageio-ffmpeg`
* `openpyxl`

Do not migrate the project to Gymnasium simply because it is newer.

---

## 11. Local highway_env Must Be Verified

The repository contains a local:

`highway_env/`

package.

Do not assume the installed PyPI `highway-env` package is the active simulator.

Before experiments, verify:

```python
import highway_env
print(highway_env.__file__)
```

The expected reproduction behavior should use the repository's local implementation unless evidence shows otherwise.

Record the exact imported path in:

`notes/reproduction_environment.md`

---

## 12. LLM Backend Policy

The original paper/repository uses OpenAI `gpt-4o-mini`.

For research integrity, distinguish two execution modes:

### Paper-Faithful Mode
- Backend: OpenAI API
- Model: `gpt-4o-mini`
- Used only for limited validation when necessary.

### Local Reproduction / Thesis Mode
- Backend: Ollama
- Model: explicitly recorded for every experiment.
- Used for repeated experiments, Memory ON/OFF comparisons,
  scenario evaluation, and later thesis development.

Ollama results must not be presented as exact numerical
reproduction of the paper's GPT-4o-mini results.

Any backend adaptation must preserve:
- prompt content
- centralized negotiation structure
- per-CAV decision structure
- action space
- parser expectations where possible
- memory semantics
- scenario semantics

Only the LLM transport/backend should change unless separately approved.

---

## 13. Secrets and API Keys

Never store API keys, passwords, tokens, or credentials directly in tracked source files.

Do not commit secrets.

If the repository contains placeholders such as:

`"your key here"`

prefer environment variables or another safe local configuration method when reproduction reaches the API stage.

Never print full credentials to logs or documentation.

Do not modify credential handling until the user approves the proposed compatibility fix.

---

## 14. Proxy Handling

The repository may contain hard-coded proxy settings such as:

`127.0.0.1:7890`

Do not assume that proxy exists on the current machine.

Before modifying proxy logic:

1. inspect current behavior;
2. test connectivity safely;
3. explain whether the proxy is required;
4. propose the smallest compatibility fix.

Do not alter system proxy settings.

---

## 15. Shared Laboratory Computer Safety

This project runs on a shared Windows laboratory workstation.

User-controlled project/software storage is primarily under:

`E:\YiZhen\`

Never:

* delete another user's files
* modify another user's environment
* modify system-wide Python packages
* modify system CUDA drivers
* alter system-wide environment variables
* terminate another user's process
* reset GPUs
* uninstall shared software
* overwrite shared datasets or models

Do not use administrative privileges unless the user explicitly authorizes it.

---

## 16. GPU Safety

CoDrivingLLM's original OpenAI-based execution does not inherently require local GPU computation.

Do not use GPU merely because GPUs are available.

Before any future GPU-intensive task:

1. run `nvidia-smi`;
2. inspect GPU utilization;
3. identify whether the task actually requires GPU;
4. never terminate another user's process.

The workstation currently provides NVIDIA GPUs, but GPU availability is not permission to consume them automatically.

---

## 17. Experiment Execution Policy

Never begin with a full experiment.

Use the following escalation sequence:

### Stage 1 — Environment inventory

* Python version
* package versions
* import paths
* Git commit
* OS
* working directory

### Stage 2 — Import preflight

* import required modules
* verify local `highway_env`
* verify Gym registration
* verify dependencies

### Stage 3 — Simulator preflight

* instantiate one environment
* reset
* inspect observation/action spaces
* perform the smallest possible deterministic step without LLM calls

### Stage 4 — LLM preflight

* validate configuration
* make the minimum necessary API call only after user approval
* save/log raw response safely
* verify parser behavior

### Stage 5 — Single episode

* one scenario
* one seed/configuration
* Memory OFF first unless otherwise instructed

### Stage 6 — Memory ON verification

* enable the existing memory path explicitly
* verify retrieval
* verify prompt injection
* verify update
* verify persistence

### Stage 7 — Small repeated test

* small number of controlled repetitions
* validate outputs and metrics

### Stage 8 — Full reproduction experiment

Only after all previous stages are successful and the user explicitly approves.

Never jump directly to 100 episodes.

---

## 18. No Accidental Execution of Entry Script

`Run_multi_CAV_LLM.py` has module-level execution behavior.

Do not import it merely for inspection.

Importing or executing it may:

* create the environment
* initialize memory
* call external APIs
* write files
* start many episodes

Inspect its source statically until an execution stage is explicitly authorized.

---

## 19. Experiment Configuration

Every experiment must record at least:

* timestamp
* Git commit
* changed files
* Conda environment
* Python version
* important package versions
* scenario
* environment ID
* Memory OFF / ON
* random seed
* LLM model
* LLM configuration
* database path/state
* number of episodes
* output directory
* command used

Do not label a run as reproduced if these are unknown.

---

## 20. Reproduction Documentation

Maintain:

### `notes/reproduction_environment.md`

Record:

* machine/environment information
* Conda environment
* Python version
* dependency versions
* import paths
* Git commit
* relevant OS/runtime details

### `notes/reproduction_log.md`

For every important reproduction attempt:

#### Attempt N

* Date/time
* Goal
* Command
* Environment
* Expected behavior
* Actual behavior
* Error/output
* Root cause
* Proposed fix
* Files affected
* Semantic impact
* Test result

Do not hide failed attempts.

### `notes/reproduction_summary.md`

Create/update after major milestones:

* what successfully reproduces
* what does not
* compatibility fixes
* paper–repository discrepancies
* Memory OFF status
* Memory ON status
* remaining limitations

---

## 21. Source Modification Protocol

Before modifying source code:

1. run `git status`;
2. identify the relevant file/function;
3. explain the current behavior;
4. explain the root cause;
5. propose the smallest change;
6. classify it as Compatibility Fix or Research-Semantic Change;
7. explain expected impact;
8. wait for user approval if semantics may change.

After modification:

1. show changed files;
2. summarize the diff;
3. run the smallest relevant test;
4. record the result;
5. update `notes/reproduction_log.md`.

Never make broad refactors during reproduction unless required.

---

## 22. Git Safety

Before modifications:

`git status`

The official repository history must remain recoverable.

Do not automatically:

* push
* force push
* merge
* rebase
* reset --hard
* clean untracked files
* delete branches
* rewrite history

without explicit user approval.

Do not commit automatically unless explicitly requested.

Research documentation and reproduction changes may remain uncommitted while being reviewed.

---

## Git Remote Policy

This repository uses two Git remotes with different roles.

### origin

`origin` refers to the user's private thesis repository:

`yizhenhong9-alt/CoDrivingLLM-Thesis`

This repository stores:

- controlled reproduction changes
- compatibility fixes
- Ollama backend adaptation
- experiment infrastructure
- research documentation
- later thesis extensions

Do not push to `origin` without explicit user approval.

### upstream

`upstream` refers to the original CoDrivingLLM repository:

`FanGShiYuu/CoDrivingLLM`

It is used only to preserve and inspect the relationship with the original project.

Never push to `upstream`.

Fetching from `upstream` for inspection is allowed.

Do not automatically:

- pull from upstream
- merge upstream changes
- rebase onto upstream
- cherry-pick upstream commits

without explicit user approval.

Before any Git operation that modifies history or communicates with a remote, report:

- current branch
- current commit
- current `git status`
- target remote
- intended operation

Local read-only commands such as:

- `git status`
- `git diff`
- `git log`
- `git remote -v`

are allowed for inspection.

---

## 23. Evaluation and Missing Paper Infrastructure

The original repository may not include:

* roundabout implementation
* 20-seed protocol
* PET aggregation
* success-rate aggregation
* travel-velocity aggregation
* reasoning ablation switches
* baseline comparison implementations

Do not silently create these and call them original repository functionality.

When missing infrastructure must later be reconstructed, clearly classify it as:

`Reconstructed Evaluation Infrastructure`

and document:

* evidence from the paper
* what was unavailable
* assumptions introduced
* implementation method
* validation method

---

## 24. Known Paper–Code Findings Are Not Automatic Bugs

Items previously identified include possible differences involving:

* scenario coverage
* memory mode
* evaluation pipeline
* seed protocol
* parser robustness
* control implementation
* safety logic
* reward implementation
* prompt/action semantics

Do not automatically fix these.

Some may represent:

* experiment configuration choices
* paper/repository version differences
* missing release artifacts
* actual bugs
* simplifications

Each must be verified separately.

---

## 25. Research Integrity

Never:

* cherry-pick successful seeds
* hide failed runs
* selectively discard undesirable results
* alter baselines to favor a proposed method
* silently change metrics
* silently change scenario difficulty
* manipulate experiment conditions to obtain desired rankings

Negative or failed results are valid research evidence.

---

## 26. Completion Criteria for Baseline Reproduction

Do not declare CoDrivingLLM reproduced merely because the script finishes.

At minimum verify:

* correct repository commit
* correct environment imports
* simulator initialization
* scenario configuration
* observation/action path
* centralized negotiation
* per-CAV LLM decision
* parser behavior
* semantic-action execution
* environment transition
* output logging
* Memory OFF behavior
* Memory ON retrieval/update/persistence
* repeatable experiment configuration

Paper-level metrics and multi-seed evaluation are separate later milestones.

---

## 27. Default Behavior When Uncertain

When uncertain:

1. stop before destructive or semantic changes;
2. explain what is known;
3. explain what is unknown;
4. provide evidence;
5. recommend the smallest next diagnostic action.

Do not guess implementation details.
