"""Replace the public example with an explicitly selected local spreadsheet."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis'))
from engine import clean, read_file
from web import validate_dataset

parser = argparse.ArgumentParser(description='更新所有访客可见的公开示例，请仅选择允许公开的数据。')
parser.add_argument('file', help='Excel 或 CSV 路径')
args = parser.parse_args()
dataset = validate_dataset(clean(read_file(args.file)))
(ROOT / 'analysis/example.json').write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'公开示例已更新：{len(dataset["rows"])} 个样方。提交 example.json 并重新部署后生效。')
