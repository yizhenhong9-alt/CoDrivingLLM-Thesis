"""Copy only selected M23 evidence into a fresh personal review folder, including partial failures."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_controller.local_memory import personal_path


def selected_files(source):
    root_names = {'git-commit.txt','memory-config.json','batch-result.json','console.txt','memory.txt','disk.txt'}
    for p in sorted(source.rglob('*')):
        if not p.is_file():
            continue
        parts = p.relative_to(source).parts
        if ((len(parts)==1 and p.name in root_names) or
            parts == ('service','service-console.txt') or
            (len(parts)==2 and parts[0].startswith('seed-') and p.name=='console.txt') or
            (len(parts)==4 and parts[0].startswith('seed-') and parts[1]=='live' and
             p.name in {'result.json','server-console.txt','traffic-console.txt'}) or
            (len(parts)==6 and parts[0].startswith('seed-') and parts[1]=='live' and parts[3]=='traffic' and
             (p.name in {'result.json','review.md'} or (p.name.startswith('step-') and p.suffix=='.json')))):
            yield p


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    args=parser.parse_args()
    source=personal_path(args.source)
    if not source.is_dir() or not source.name.startswith('M23-intersection-memory-on-20seeds-'):
        raise ValueError('Existing M23 source run required')
    target=Path(tempfile.mkdtemp(prefix='M23-review-',dir=str(personal_path(Path('/home/nclab/Yizhen/runs')))))
    for path in selected_files(source):
        personal_path(path)
        dest=target/path.relative_to(source)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(str(path),str(dest))
    (target/'SOURCE.txt').write_text(source.as_posix()+'\n',encoding='utf-8')
    lines=['{}  ./{}'.format(hashlib.sha256(p.read_bytes()).hexdigest(),p.relative_to(target).as_posix())
           for p in sorted(target.rglob('*')) if p.is_file()]
    (target/'SHA256SUMS').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Review folder (copy this folder): '+str(target),flush=True)


if __name__=='__main__':
    main()
