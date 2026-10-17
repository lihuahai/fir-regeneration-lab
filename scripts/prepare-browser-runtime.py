"""Stage a pinned Python runtime and only the wheels used by the analysis engine."""
import ast, concurrent.futures, hashlib, json, shutil, urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'public/python-runtime';out.mkdir(parents=True,exist_ok=True)
base=root/'node_modules/pyodide'
for name in ['pyodide.mjs','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json']:
    shutil.copy2(base/name,out/name)
lock=json.loads((base/'pyodide-lock.json').read_text());packages=lock['packages'];needed=set()
def require(name):
    if name in needed:return
    needed.add(name)
    for dep in packages[name]['depends']:require(dep)
require('statsmodels')
require('scikit-learn')
def download(name):
    item=packages[name];target=out/item['file_name']
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:return name
    url='https://cdn.jsdelivr.net/pyodide/v314.0.7/full/'+item['file_name']
    with urllib.request.urlopen(url,timeout=120) as response:raw=response.read()
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Checksum mismatch: '+name)
    target.write_bytes(raw)
    return name
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for name in pool.map(download,sorted(needed)):print('Ready:',name,flush=True)
analysis=root/'public/analysis';analysis.mkdir(exist_ok=True)
for name in ['engine.py','importance.py','example.json']:shutil.copy2(root/'analysis'/name,analysis/name)
# Reuse the exact validated import rules; Flask and server persistence are excluded.
src=(root/'analysis/web.py').read_text();tree=ast.parse(src)
functions=[ast.get_source_segment(src,node) for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in {'validate_dataset','validate_config','source','read_upload'}]
imports='import base64, binascii, csv, hashlib, io, json, math, re, time, zipfile\nfrom pathlib import Path\nimport openpyxl\nfrom engine import parse_table\nMAX_ROWS, MAX_COLUMNS, MAX_BYTES = 300, 40, 5 * 1024 * 1024\n\n'
(analysis/'browser_io.py').write_text(imports+'\n\n'.join(functions)+'\n')
print('Total runtime MB:',round(sum(p.stat().st_size for p in out.iterdir())/1024/1024,1))
