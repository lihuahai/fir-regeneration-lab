"""Make a deployment archive from a validated online build and explicit source files."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
stage=root/'deploy-package'
if stage.exists():shutil.rmtree(stage)
stage.mkdir()
files=['Dockerfile','.dockerignore','.gitignore','render.yaml','requirements.txt','gunicorn.conf.py','README.md','在线部署说明.md',
       'package.json','package-lock.json','next.config.ts','vite.config.ts','tsconfig.json','eslint.config.mjs','postcss.config.mjs','cloudflare-env.d.ts',
       '.openai/hosting.json','analysis/engine.py','analysis/web.py','analysis/example.json','analysis/test_web.py',
       'scripts/stage-online.mjs','scripts/update-example.py','scripts/package-online.py','tests/rendered-html.test.mjs']
folders=['site','app','build','worker','public','db','drizzle']
for name in files:
    target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,target)
for name in folders:shutil.copytree(root/name,stage/name)
assert '在线研究工具' in (stage/'site/index.html').read_text()
manifest={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.rglob('*')) if p.is_file()}
(stage/'BUILD_MANIFEST.json').write_text(json.dumps({'build':'2026-10-17','frontend':'vinext static export','backend':'Flask / Gunicorn','files':manifest},ensure_ascii=False,indent=2)+'\n')
archive=root/'outputs/冷杉网站_Render部署包.zip'
archive.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob('*')):
        if p.is_file():z.write(p,'fir-regeneration-online/'+str(p.relative_to(stage)))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert 'fir-regeneration-online/Dockerfile' in z.namelist()
    assert 'fir-regeneration-online/site/index.html' in z.namelist()
    assert not any('/data/' in name or '/work/' in name or '.env' in name for name in z.namelist())
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'files':len(manifest)+1,'folder':str(stage)},ensure_ascii=False))
