"""M08: offline tokenizer-only measurement of saved M05 prompt messages.

Run in the existing Spark inference environment, not the simulation environment.
No model weights are loaded. No network, installation or service startup.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from uuid import uuid4

MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507-FP8"
REVISION = "5a5a776300a41aaa681dd7ff0106608ef2bc90db"


def measure(tokenizer, fixture, output_tokens, context_limit):
    if type(output_tokens) is not int or output_tokens < 1:
        raise ValueError("Output token budget must be positive")
    if type(context_limit) is not int or context_limit < 1:
        raise ValueError("Context limit must be positive")
    if fixture.get("model") != MODEL or fixture.get("status") != "validated_not_applied":
        raise ValueError("Expected successful M05 fixture for the specified model")
    if fixture.get("mode") != "fixture":
        raise ValueError("This tool measures fixture prompts only")
    calls = fixture.get("calls")
    if not isinstance(calls, list) or not calls:
        raise ValueError("No prompt calls found")
    rows = []
    for index, call in enumerate(calls):
        messages = call.get("messages")
        if not isinstance(messages, list) or not messages or any(
                not isinstance(m, dict) or not isinstance(m.get("content"), str)
                or m.get("role") not in ("system", "user", "assistant") for m in messages):
            raise ValueError("Invalid saved messages")
        rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        if not isinstance(rendered, str):
            raise ValueError("Expected rendered chat template text")
        tokens = tokenizer.encode(rendered, add_special_tokens=False)
        if not isinstance(tokens, list) or any(type(token) is not int for token in tokens):
            raise ValueError("Expected flat token ID list")
        required = len(tokens) + output_tokens
        rows.append(dict(call=index, stage=call.get("stage"),
                         vehicle_id=call.get("context", {}).get("vehicle_id"),
                         input_tokens=len(tokens), reserved_output_tokens=output_tokens,
                         required_tokens=required, context_limit=context_limit,
                         remaining_tokens=context_limit-required, fits=required <= context_limit,
                         rendered_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest()))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--context-limit", type=int, default=2048)
    args = parser.parse_args()
    if os.name != "posix":
        parser.error("Tokenizer measurement is intended for Spark; do not load it on Windows")
    for path in [args.model_dir, args.output_dir] + args.fixtures:
        try:
            path.resolve().relative_to(Path("/home/nclab/Yizhen"))
        except ValueError:
            parser.error("All paths must stay inside /home/nclab/Yizhen")
    if not args.model_dir.is_dir() or any(not file.is_file() for file in args.fixtures):
        parser.error("Model directory or fixture file is missing")
    folder = args.output_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    for name, child in (("HF_HOME", "hf-cache"), ("XDG_CACHE_HOME", "cache"),
                        ("TMPDIR", "tmp")):
        location = folder / child
        location.mkdir(exist_ok=True)
        os.environ[name] = str(location)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", CUDA_VISIBLE_DEVICES="",
                      TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="1")
    report = dict(status="running", model=MODEL, expected_revision=REVISION,
                  revision_evidence="Expected revision from handoff; this tool does not reverify weights",
                  model_dir=str(args.model_dir.resolve()), python=sys.version, fixtures=[],
                  source_sha256=hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
                  limitation="Seed-0 fixture prompts; no real Qwen response, memory-on or multi-seed coverage")
    exit_code = 0
    try:
        # Import only in the explicitly invoked Spark CLI, never in local tests.
        import transformers
        from transformers import AutoTokenizer
        from unittest.mock import patch

        def block_network(*unused, **unused_kwargs):
            raise RuntimeError("Network disabled during offline token counting")

        with patch("socket.socket.connect", block_network), \
                patch("socket.socket.connect_ex", block_network), \
                patch("socket.create_connection", block_network):
            tokenizer = AutoTokenizer.from_pretrained(str(args.model_dir.resolve()),
                local_files_only=True, trust_remote_code=False)
            report["transformers_version"] = transformers.__version__
            report["tokenizer_class"] = type(tokenizer).__name__
            report["chat_template_sha256"] = hashlib.sha256(
                json.dumps(tokenizer.chat_template, ensure_ascii=False).encode("utf-8")).hexdigest()
            for path in args.fixtures:
                raw = path.read_bytes()
                fixture = json.loads(raw.decode("utf-8-sig"))
                rows = measure(tokenizer, fixture, args.output_tokens, args.context_limit)
                report["fixtures"].append(dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                    prompt_version=fixture.get("prompt_version"), parser_mode=fixture.get("parser_mode"),
                    git_commit=fixture.get("git_commit"), rows=rows))
        report["all_fit"] = all(row["fits"] for entry in report["fixtures"] for row in entry["rows"])
        report["status"] = "measured" if report["all_fit"] else "context_exceeded"
        exit_code = 0 if report["all_fit"] else 2
    except Exception:
        report.update(status="failed", error=traceback.format_exc())
        exit_code = 1
    output = folder / "result.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Status: " + report["status"])
    for fixture in report["fixtures"]:
        print("Parser: " + str(fixture["parser_mode"]))
        for row in fixture["rows"]:
            print("  {} vehicle={} input={} reserve={} fits={}".format(
                row["stage"], row["vehicle_id"], row["input_tokens"], row["reserved_output_tokens"], row["fits"]))
    print("Result: " + str(output.resolve()))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
