"""Run M01-M05 checks and simulator fixtures, without starting a model.

Use the existing Spark simulation interpreter. All child processes are serial;
outputs and process-local caches stay below --output-dir.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--resume-fixtures", action="store_true",
                        help="Run the M07 path regression and fixtures; do not repeat passed suites")
    args = parser.parse_args()
    base = args.output_dir.resolve()
    if os.name == "posix":
        try:
            base.relative_to(Path("/home/nclab/Yizhen"))
        except ValueError:
            parser.error("Outputs must stay inside /home/nclab/Yizhen")
    folder = base / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    folder.mkdir(parents=True)
    process_env = os.environ.copy()
    for name, subdir in (("XDG_CACHE_HOME", "cache"), ("MPLCONFIGDIR", "matplotlib"),
                         ("TMPDIR", "tmp"), ("TEMP", "tmp"), ("TMP", "tmp")):
        location = folder / subdir
        location.mkdir(exist_ok=True)
        process_env[name] = str(location)
    process_env.update(PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="",
                       MPLBACKEND="Agg", SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
                       OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1")
    report = dict(status="running", python=sys.version, executable=sys.executable,
                  mode="offline_no_model", seed=args.seed, commands=[])
    output = folder / "result.json"

    def save():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    commands = [[sys.executable, "validation/" + name] for name in (
        "check_output_schema.py", "check_vehicle_actions.py", "check_memory_off.py",
        "check_qwen_single_step.py")]
    if args.resume_fixtures:
        commands = [[sys.executable, "validation/check_qwen_single_step.py",
                     "TransportTests.test_source_hash_record_accepts_relative_script_path"]]
    for mode in ("strict", "legacy"):
        commands.append([sys.executable, "validation/run_qwen_single_step.py", "--mode", "fixture",
                         "--parser", mode, "--seed", str(args.seed), "--output-dir", str(folder / mode)])
    save()
    try:
        for index, command in enumerate(commands):
            print("Running: " + " ".join(command), flush=True)
            log = folder / ("command-{}.txt".format(index + 1))
            with log.open("w", encoding="utf-8") as console:
                result = subprocess.run(command, cwd=str(ROOT), env=process_env,
                                        stdout=console, stderr=subprocess.STDOUT)
            report["commands"].append(dict(command=command, exit_code=result.returncode, log=log.name))
            save()
            if result.returncode != 0:
                raise RuntimeError("Command failed; inspect " + log.name)
        for mode in ("strict", "legacy"):
            files = list((folder / mode).glob("*.json"))
            if len(files) != 1:
                raise RuntimeError("Expected one fixture report for " + mode)
            fixture = json.loads(files[0].read_text(encoding="utf-8"))
            if (fixture["status"] != "validated_not_applied" or fixture["environment_steps"] != 0
                    or fixture["actual_environment_steps"] != 0 or fixture["memory_module_imported"]):
                raise RuntimeError("Fixture status/step/memory check failed: " + mode)
            if len(fixture["calls"]) != 1 + len(fixture["initial_vehicles"]):
                raise RuntimeError("Unexpected call count: " + mode)
            if any(call["sent_to_model"] for call in fixture["calls"]):
                raise RuntimeError("Fixture must not call a model")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=str(exc))
    finally:
        save()
        print("Status: " + report["status"])
        print("Result: " + str(output))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
