"""M20-R4 Spark-only metadata plan; no ML imports or package/model installation."""
import argparse
import hashlib
from html.parser import HTMLParser
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import personal_path

TORCH = '2.9.1+cpu'
TRANSFORMERS = '5.22.2'
INDEX = 'https://download.pytorch.org/whl/cpu/torch/'
WHEEL = 'torch-2.9.1+cpu-cp312-cp312-manylinux_2_28_aarch64.whl'


def name_key(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def freeze_map(text):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s]+)', line)
        if not match:
            raise ValueError('Baseline must contain only exact package pins')
        key = name_key(match.group(1))
        if key in result:
            raise ValueError('Duplicate baseline distribution')
        result[key] = match.group(2)
    if not result:
        raise ValueError('Empty package baseline')
    return result


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(value for key, value in attrs if key == 'href' and value)


def select_cpu_wheel(html):
    parser = Links()
    parser.feed(html)
    matches = set()
    for link in parser.links:
        url = urljoin(INDEX, link)
        parts = urlsplit(url)
        if unquote(parts.path.rsplit('/', 1)[-1]) != WHEEL:
            continue
        if (parts.scheme != 'https' or parts.hostname not in ('download.pytorch.org', 'download-r2.pytorch.org') or
                not re.fullmatch(r'sha256=[0-9a-fA-F]{64}', parts.fragment) or parts.username):
            raise ValueError('Expected official CPU wheel URL with SHA256')
        matches.add(url)
    if len(matches) != 1:
        raise ValueError('Expected exactly one pinned ARM64/CPython312 CPU wheel')
    return matches.pop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'linux' or platform.machine() != 'aarch64' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Run manually on Spark ARM64 Python 3.12')
    personal_path(ROOT)
    expected_env = Path('/home/nclab/Yizhen/envs/memory-chroma0415-py312')
    if Path(sys.prefix) != expected_env:
        raise ValueError('Expected the dedicated memory environment')
    personal_path(Path(sys.prefix))
    baseline_path = personal_path(args.baseline)
    output = personal_path(args.output_dir)
    if not output.is_dir():
        raise ValueError('Output directory must already exist')
    baseline = freeze_map(baseline_path.read_text(encoding='utf-8'))
    current = {name_key(dist.metadata['Name']): dist.version for dist in importlib.metadata.distributions()}
    if current != baseline:
        raise ValueError('Current packages differ from the verified Chroma baseline; no automatic repair')
    if baseline.get('chromadb') != '0.4.15' or baseline.get('numpy') != '1.26.4' or baseline.get('chroma-hnswlib') != '0.7.3':
        raise ValueError('Unexpected Chroma baseline')
    for name in ('torch', 'transformers'):
        if name in baseline:
            raise ValueError('Unexpected pre-existing embedding runtime')
    with urlopen(INDEX, timeout=30) as response:
        html = response.read(4*1024*1024+1)
    if len(html) > 4*1024*1024:
        raise ValueError('CPU index response too large')
    wheel_url = select_cpu_wheel(html.decode('utf-8'))
    constraints = ''.join('{}=={}\n'.format(key, value) for key, value in sorted(baseline.items()))
    requirements = 'torch @ '+wheel_url+'\ntransformers=='+TRANSFORMERS+'\nsafetensors\n'
    (output/'constraints.txt').write_text(constraints, encoding='utf-8')
    (output/'requirements.in').write_text(requirements, encoding='utf-8')
    report = dict(status='ready_for_dry_run', baseline=str(baseline_path),
                  baseline_sha256=hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                  frozen_packages=len(baseline), torch=TORCH, transformers=TRANSFORMERS,
                  cpu_wheel_url=wheel_url, index=INDEX,
                  index_sha256=hashlib.sha256(html).hexdigest(),
                  package_installation=False, model_download=False, model_loaded=False)
    (output/'plan.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
