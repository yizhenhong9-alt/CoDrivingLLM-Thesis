"""M21-R3 send exactly two approved frozen memory prompts; never env.step."""
import argparse
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import personal_path
from llm_controller.memory_replay import load_config, run_replay
from llm_controller.qwen_transport import LocalQwen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or sys.version_info[:2] != (3, 8) or Path(sys.prefix) != Path('/home/nclab/Yizhen/envs/codriving-sim-py38'):
        raise RuntimeError('Existing Spark simulation Python 3.8 required')
    personal_path(ROOT)
    bundle = load_config(args.config)
    folder = personal_path(args.output_dir)
    folder.mkdir(parents=True, exist_ok=False)
    report = {}
    def save(value):
        temp = folder/'result.tmp'
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        temp.replace(folder/'result.json')
    transport = LocalQwen(max_tokens=256)
    try:
        transport.preflight()
        run_replay(bundle, transport, report, save)
    except BaseException:
        report.update(status='failed', error=traceback.format_exc())
        raise
    finally:
        save(report)


if __name__ == '__main__':
    main()
