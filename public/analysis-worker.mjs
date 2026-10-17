import {loadPyodide} from './python-runtime/pyodide.mjs';

let ready;
const status = text => self.postMessage({type:'status', text});
async function initialize() {
  status('首次打开正在准备分析组件，请稍候…');
  const py = await loadPyodide({indexURL:new URL('./python-runtime/',self.location.href).href});
  status('正在加载统计分析功能…');
  await py.loadPackage(['statsmodels']);
  const fetchFile = async url => {
    const response = await fetch(url);
    if (!response.ok) throw new Error('分析组件下载失败，请检查网络后重试。');
    return new Uint8Array(await response.arrayBuffer());
  };
  for (const name of ['et_xmlfile-2.0.0-py3-none-any.whl','openpyxl-3.1.5-py2.py3-none-any.whl']) {
    py.FS.writeFile('/tmp/'+name,await fetchFile('./python-runtime/'+name));
    py.runPython(`import zipfile\nwith zipfile.ZipFile('/tmp/${name}') as wheel:\n    wheel.extractall('/home/pyodide')`);
    py.FS.unlink('/tmp/'+name);
  }
  for (const name of ['engine.py','browser_io.py']) {
    py.FS.writeFile('/home/pyodide/'+name,await fetchFile('./analysis/'+name));
  }
  py.runPython('import json\nfrom engine import analyze, permutation_indices\nfrom browser_io import validate_dataset, validate_config, read_upload, source');
  status('');
  return py;
}

let chain = Promise.resolve();
self.onmessage = ({data}) => {
  chain = chain.catch(()=>{}).then(async()=>{
    const {id,path,body} = data;
    try {
      if (!ready) ready=initialize();
      const py=await ready;
      py.globals.set('_request_json',JSON.stringify(body));
      let result;
      if (path==='analyze') {
        result=py.runPython("_request=json.loads(_request_json)\njson.dumps(analyze(validate_dataset(_request['dataset']),validate_config(_request.get('config',{}))),ensure_ascii=False,allow_nan=False)");
        py.runPython('permutation_indices.cache_clear()');
      } else if (path==='import') {
        result=py.runPython("json.dumps(source(read_upload(json.loads(_request_json)),'import'),ensure_ascii=False,allow_nan=False)");
      } else throw new Error('不支持的操作。');
      py.globals.delete('_request_json');
      self.postMessage({id,result:JSON.parse(result)});
    } catch (error) {
      status('');
      const message=String(error?.message??error);
      const human=message.match(/(?:ValueError|TypeError|KeyError): ([^\n]+)/)?.[1];
      self.postMessage({id,error:human??'分析组件未能完成计算，请检查数据或刷新页面重试。',detail:message});
    }
  });
};
