"""Zip the built static site for Netlify Drop, with index.html at its root."""
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
assert (root/'site/index.html').is_file()
assert (root/'site/python-runtime/pyodide.asm.wasm').is_file()
target=root/'outputs/冷杉网站_Netlify部署包.zip'
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted((root/'site').rglob('*')):
        if p.is_file():z.write(p,p.relative_to(root/'site'))
print(target)
