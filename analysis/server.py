"""Local-only data service. Watches the source file without writing to it."""
import base64
import hashlib
import json
import os
import threading
import time
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from engine import read_file, analyze, clean

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('FIR_DATA_DIR', str(ROOT / 'data')))
DATA.mkdir(exist_ok=True, parents=True)
ORIGINAL = Path(os.environ.get('FIR_SOURCE', '/Users/hhl/Desktop/实验冷杉.xlsx'))
PORT = int(os.environ.get('FIR_API_PORT', '8768'))
LOCK = threading.RLock()


def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, data):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


@lru_cache(maxsize=8)
def load_source(path, mtime, size):
    return read_file(path)


def get_data():
    state=read_json(DATA/'state.json', {'mode':'original'})
    if state['mode']=='draft':
        p=DATA/'draft.json'
        dataset=read_json(p,{})
    else:
        p=ORIGINAL if state['mode']=='original' else DATA/state['filename']
        st=p.stat()
        dataset=dict(load_source(str(p),st.st_mtime_ns,st.st_size))
        if state.get('originalName'): dataset['name']=state['originalName']
    st=p.stat()
    version=f"{state['mode']}:{st.st_mtime_ns}:{st.st_size}"
    return dict(dataset=dataset,version=version,mode=state['mode'],modified=st.st_mtime,
                sourcePath=str(ORIGINAL),sourceName=dataset.get('name',ORIGINAL.name),config=read_json(DATA/'config.json',{}))


@lru_cache(maxsize=20)
def compute(data_string, config_string):
    return analyze(json.loads(data_string),json.loads(config_string))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def cors(self):
        origin=self.headers.get('Origin','')
        if origin and urlparse(origin).hostname not in ('localhost','127.0.0.1'):
            return False
        return True

    def reply(self, data, code=200):
        body=json.dumps(clean(data),ensure_ascii=False,allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        origin=self.headers.get('Origin')
        if origin and self.cors():
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if not self.cors(): return self.reply({'error':'仅允许本机网页访问。'},403)
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin','http://127.0.0.1:5173'))
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.end_headers()

    def do_GET(self):
        if not self.cors(): return self.reply({'error':'仅允许本机网页访问。'},403)
        try:
            if self.path=='/api/health':
                return self.reply({'app':'fir-regeneration','status':'ready','version':1})
            if self.path=='/api/data':
                with LOCK: data=get_data()
                return self.reply(data)
            return self.reply({'error':'未找到接口'},404)
        except Exception as e:
            self.reply({'error':f'读取数据失败：{e}。若 Excel 正在保存，请稍后重试。'},400)

    def do_POST(self):
        if not self.cors(): return self.reply({'error':'仅允许本机网页访问。'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>20*1024*1024: raise ValueError('文件超过 20 MB，请使用样方汇总数据。')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/analyze':
                result=compute(json.dumps(body['dataset'],sort_keys=True,ensure_ascii=False),json.dumps(body.get('config',{}),sort_keys=True))
                return self.reply(result)
            if self.path=='/api/importance':
                from importance import fit_importance
                from web import validate_dataset, validate_config
                return self.reply(fit_importance(validate_dataset(body['dataset']), validate_config(body.get('config', {}))))
            with LOCK:
                if self.path=='/api/draft':
                    dataset=body['dataset']
                    if len(dataset.get('rows',[]))>5000: raise ValueError('当前交互分析上限为 5,000 个样方。')
                    from engine import prepared
                    prepared(dataset,body.get('config',{}))
                    save_json(DATA/'draft.json',dataset)
                    save_json(DATA/'state.json',{'mode':'draft'})
                    return self.reply(get_data())
                if self.path=='/api/config':
                    save_json(DATA/'config.json',body)
                    return self.reply({'ok':True})
                if self.path=='/api/source':
                    if body.get('mode')!='original': raise ValueError('未知数据来源。')
                    read_file(ORIGINAL)
                    save_json(DATA/'state.json',{'mode':'original'})
                    return self.reply(get_data())
                if self.path=='/api/import':
                    ext=Path(body['name']).suffix.lower()
                    if ext not in ('.xlsx','.csv'): raise ValueError('支持 .xlsx 或 .csv。')
                    raw=base64.b64decode(body['base64'],validate=True)
                    filename='import-'+hashlib.sha256(raw).hexdigest()[:12]+ext
                    p=DATA/filename
                    p.write_bytes(raw)
                    dataset=read_file(p)
                    if not dataset['rows']: raise ValueError('文件中未找到有效样方。')
                    save_json(DATA/'state.json',{'mode':'import','filename':filename,'originalName':Path(body['name']).name})
                    return self.reply(get_data())
            return self.reply({'error':'未找到接口'},404)
        except Exception as e:
            self.reply({'error':str(e)},400)


if __name__=='__main__':
    print(f'Fir analysis API: http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
