"""Build the standalone, offline report from the selected qualitative annotations."""
import csv
import json
import argparse
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Rebuild an existing media comparison.')
parser.add_argument('--case', choices=['sailing', 'grantham'], default='sailing')
args = parser.parse_args()
if args.case == 'sailing':
    runpy.run_path(str(ROOT / 'cases/sailing/build_report.py'), run_name='__main__')
    raise SystemExit(0)
with (ROOT / 'data/annotated-examples.csv').open() as source:
    examples = list(csv.DictReader(source))
template = (ROOT / 'report-template.html').read_text()
data = json.dumps(examples, ensure_ascii=False).replace('<', '\\u003c')
(ROOT / 'index.html').write_text(template.replace('__EXAMPLES_JSON__', data))
print(f'Built index.html with {len(examples)} annotated examples')
