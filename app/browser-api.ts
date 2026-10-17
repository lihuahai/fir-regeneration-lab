import type {Source} from './types';

let worker:Worker|null=null;
let sequence=0;
const pending=new Map<number,{resolve:(v:unknown)=>void;reject:(e:Error)=>void;cleanup:()=>void}>();
const listeners=new Set<(text:string)=>void>();
export function subscribeComputeStatus(fn:(text:string)=>void){listeners.add(fn);return()=>{listeners.delete(fn);};}
function getWorker(){
  if(!worker){
    worker=new Worker('/analysis-worker.mjs',{type:'module'});
    worker.onmessage=({data})=>{
      if(data.type==='status'){listeners.forEach(fn=>fn(data.text));return;}
      const task=pending.get(data.id);if(!task)return;pending.delete(data.id);task.cleanup();
      if(data.error){console.error(data.detail);task.reject(new Error(data.error));}else task.resolve(data.result);
    };
    worker.onerror=()=>{pending.forEach(p=>{p.cleanup();p.reject(new Error('分析组件加载失败，请刷新页面重试。'));});pending.clear();worker?.terminate();worker=null;};
  }
  return worker;
}
export async function browserApi(path:string,body?:unknown,signal?:AbortSignal):Promise<unknown>{
  if(path==='data'){
    const response=await fetch('/analysis/example.json',{signal,cache:'no-cache'});
    if(!response.ok)throw new Error('示例数据未能载入，请刷新重试。');
    const dataset=await response.json();
    return {dataset,mode:'example',sourceName:dataset.name,sourcePath:'',version:'browser-example-v1',modified:Date.now()/1000,config:{}} satisfies Source;
  }
  return new Promise((resolve,reject)=>{
    if(signal?.aborted){reject(new DOMException('已取消','AbortError'));return;}
    const id=++sequence;
    const abort=()=>{pending.delete(id);reject(new DOMException('已取消','AbortError'));};
    pending.set(id,{resolve,reject,cleanup:()=>signal?.removeEventListener('abort',abort)});
    signal?.addEventListener('abort',abort,{once:true});
    getWorker().postMessage({id,path,body});
  });
}
