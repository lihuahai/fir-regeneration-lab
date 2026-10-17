"use client";
import {useEffect,useId,useState} from 'react';
import type {Analysis,Config,Dataset,ImportanceResult,ImportanceRun} from './types';
import {Panel,Note,Metric,ModelSection,labelOf} from './sections';
import {ExportSVG,fmt} from './charts';
import {download} from './report';

const OUTCOMES=new Set(['n1','n2','n3','h1','h2','h3','d1','d2','d3','total','presence','laterShare','density']);
const METHODS=[['rf','随机森林'],['extra','极端随机树'],['boost','梯度提升树']];
type Compute=(path:string,body?:unknown,signal?:AbortSignal)=>Promise<ImportanceResult>;

export function ModelWorkbench(props:{a:Analysis;dataset:Dataset;config:Config;setConfig:(c:Config)=>void;compute:Compute;run:ImportanceRun|null;onResult:(r:ImportanceRun)=>void;status:string}){
  const [view,setView]=useState('trees');
  return <><div className="model-tabs" role="tablist" aria-label="多因子分析任务"><button role="tab" aria-selected={view==='trees'} onClick={()=>setView('trees')}>因子贡献与规律 · 树模型</button><button role="tab" aria-selected={view==='counts'} onClick={()=>setView('counts')}>计数回归 · Poisson / NB2</button></div>{view==='trees'?<ImportanceSection {...props}/>:<ModelSection a={props.a} config={props.config} setConfig={props.setConfig}/>}</>;
}

function ImportanceSection({a,dataset,config,setConfig,compute,run,onResult,status}:{a:Analysis;dataset:Dataset;config:Config;setConfig:(c:Config)=>void;compute:Compute;run:ImportanceRun|null;onResult:(r:ImportanceRun)=>void;status:string}){
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0),[axis,setAxis]=useState('');
  const eligible=a.columns.filter(c=>['environment','categorical'].includes(c.role)&&!OUTCOMES.has(c.key)&&c.key!==config.areaColumn);
  const selected=config.mlPredictors??eligible.map(c=>c.key);
  const signature=JSON.stringify({dataset,config});
  const result=run?.signature===signature?run.result:null;
  const savedSignature=run?.signature;
  useEffect(()=>{
    if(savedSignature===signature)return;
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      setBusy(true);setError('');
      compute('importance',JSON.parse(signature),controller.signal).then(r=>{onResult({signature,result:r});setBusy(false);}).catch(e=>{if(e.name!=='AbortError'){setError(e.message);setBusy(false);}});
    },900);
    return()=>{clearTimeout(timer);controller.abort();};
  },[signature,savedSignature,retry,compute,onResult]);
  const label=(k:string)=>labelOf(a,k);
  const nf=result?.folds.length??4;
  const first=result?.importance[0];
  const curve=result?.dependence.find(d=>d.key===axis)??result?.dependence.find(d=>d.key===first?.key);
  const response=label(a.target);
  const pending=!result&&!error;
  const exportRows=()=>{if(!result)return;const cell=(v:unknown)=>'"'+String(v??'').replace(/"/g,'""')+'"';download('环境因子_预测重要性.csv','\ufeff'+[
    ['模型','响应','因子','验证误差增量','置换SD','相对预测重要性(%)','正增量折数','验证折数','交叉验证R2','相对基准误差改善(%)'],
    ...result.importance.map(r=>[result.name,response,label(r.key),r.delta,r.sd,r.share,r.positiveFolds,nf,result.metrics.r2,(result.metrics.skill??0)*100])
  ].map(row=>row.map(cell).join(',')).join('\r\n'),'text/csv;charset=utf-8');};
  return <>
    <Panel title="哪个环境因子更有预测价值？" subtitle="三种树模型均可捕捉非线性；响应指标由上方切换，修改数据或勾选因子后自动重算">
      <div className="tree-config"><div><label className="field-title" htmlFor="tree-model">树模型</label><select id="tree-model" aria-label="树模型" value={config.mlMethod??'rf'} onChange={e=>setConfig({...config,mlMethod:e.target.value})}>{METHODS.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select><p>按大样地分成 4 折验证，参数固定。更换模型后比较排序是否一致；当前样本不作自动调参。</p></div><div><div className="factor-heading"><span className="field-title">环境因子 · {selected.length} 项</span><button className="text-button" onClick={()=>setConfig({...config,mlPredictors:eligible.map(c=>c.key).slice(0,20)})}>全选</button></div><div className="checkbox-group tree-factors">{eligible.map(c=><label key={c.key}><input type="checkbox" aria-label={'因子 · '+c.label} checked={selected.includes(c.key)} disabled={!selected.includes(c.key)&&selected.length>=20} onChange={e=>setConfig({...config,mlPredictors:e.target.checked?[...selected,c.key]:selected.filter(k=>k!==c.key)})}/>{c.label}{c.role==='categorical'&&<small>分类</small>}</label>)}</div></div></div>
      <div className="tree-actions"><button className="secondary" disabled={busy||pending} onClick={()=>{onResult({signature:'',result:result!});setError('');setRetry(x=>x+1);}}>重新拟合</button><span role="status">{pending?(status||'正在准备大样地验证与因子贡献…'):error?'当前设置需调整':`${result?.name} · ${response} · 已计算`}</span>{result&&<button className="text-button" onClick={exportRows}>导出重要性 CSV ↗</button>}</div>
    </Panel>
    {error&&<div className="error-banner" role="alert">{error} 请调整因子或响应指标后重试。</div>}
    {pending&&<div className="loading"><div className="loading-ring"/><h3>{status||'正在比较环境因子的预测贡献'}</h3><p>每个大样地整体留出；首次计算需要加载树模型组件。</p></div>}
    {result&&<>
      <Note>当前仅 {result.blocks} 个独立大样地。这里的百分比是<strong>相对预测重要性</strong>，不等于解释率、独立生态贡献或因果效应。{result.binary?'当前采用分类模型，预测更新出现概率。':'当前采用回归模型。'}同一大样地内的样方没有拆到训练和验证两侧。</Note>
      <div className="metric-grid tree-metrics"><Metric label={result.binary?'留出验证 AUC':'留出验证 R²'} value={fmt(result.binary?result.metrics.auc:result.metrics.r2,3)} detail={result.binary?'0.5 附近表示区分能力有限':'来自所有未参与训练的预测；可为负值'}/><Metric label={result.binary?'Brier 分数':'留出验证 RMSE'} value={fmt(result.binary?result.metrics.brier:result.metrics.rmse,3)} detail={result.binary?'概率预测误差，越小越好':response+'的预测误差，越小越好'}/><Metric label="相对均值基准改善" value={fmt((result.metrics.skill??0)*100,1)} unit="%" detail="基准只使用训练折均值；负值表示不如基准"/><Metric label="有效样方 / 大样地" value={`${result.n} / ${result.blocks}`} detail={`排除缺失 ${result.excluded} 个样方 · ${nf} 折验证`}/></div>
      <div className="tree-summary"><h2>{!result.reliable?'当前模型不足以支持因子贡献结论':first&&first.delta>0?`${label(first.key)}的相对预测重要性最高`:'当前未识别出正的预测重要性'}</h2><p>{result.reliable&&first?`在 ${nf} 折中的 ${first.positiveFolds} 折打乱该因子会增加误差；${first.firstFolds} 折排第一。其百分比为 ${fmt(first.share,1)}%，取决于所选模型、响应和其他因子。`:'模型未超过训练均值基准，或回归 R²≤0；保留原始误差增量供检查，暂不报告百分比。'}</p></div>
      <Panel title="因子重要性排序" subtitle={`按 ${result.binary?'ΔBrier':'ΔMSE'} 排序；正值越大，模型越依赖该因子。负值表示打乱后预测反而改善。`}><ImportanceBars result={result} label={label}/><p className="chart-foot">百分比仅对正的平均误差增量归一化；其总和为 100%，并非模型解释了 100% 的更新变异。置换 SD 只反映重复打乱的波动，不是置信区间。</p><div className="table-scroll"><table><thead><tr><th>环境因子</th><th>误差增量</th><th>置换 SD</th><th>相对重要性</th><th>正增量折数</th><th>排第一折数</th></tr></thead><tbody>{result.importance.map(r=><tr key={r.key}><th>{label(r.key)}</th><td>{fmt(r.delta,3)}</td><td>{fmt(r.sd,3)}</td><td>{r.share===null?'暂不报告':fmt(r.share,1)+'%'}</td><td>{r.positiveFolds}/{nf}</td><td>{r.firstFolds}/{nf}</td></tr>)}</tbody></table></div></Panel>
      <div className="two-col"><Panel title="环境梯度上的预测规律" subtitle="偏依赖：改变一个因子，对其他因子的观测分布取平均"><div className="inline-control"><label>查看因子<select aria-label="偏依赖环境因子" value={curve?.key??''} onChange={e=>setAxis(e.target.value)}>{result.importance.map(r=><option key={r.key} value={r.key}>{label(r.key)}</option>)}</select></label></div>{curve&&<DependencePlot curve={curve} name={label(curve.key)} response={result.binary?'更新出现概率':response}/>}<p className="chart-foot">用全部有效样本重新拟合后绘制，曲线没有因果含义或置信区间。连续变量显示 5%–95% 分位范围（取值少时全部显示）；不以峰值认定最适条件。</p></Panel><Panel title="对新大样地能预测多好？" subtitle="每个点都是留出预测；虚线为预测值等于观测值"><PredictionPlot result={result}/><p className="chart-foot">{result.binary?'横轴为真实 0/1 状态，纵轴为预测概率。':'预测值偏离虚线越远，误差越大。'}留出验证 MAE = {fmt(result.metrics.mae,3)}；均值基准 RMSE = {fmt(result.metrics.baselineRmse,3)}。</p></Panel></div>
      <Panel title="相关因子与排序稳定性" subtitle="相关因子会互相替代，不能把排序直接当作独立贡献">{result.correlated.length?<><p className="small-note">以下数值因子的总体 Spearman |ρ|≥0.70，重要性可能分摊；可按生态依据保留其中一个后比较模型。</p><div className="table-scroll"><table><thead><tr><th>因子 A</th><th>因子 B</th><th>总体 ρ</th></tr></thead><tbody>{result.correlated.map(c=><tr key={c.a+c.b}><th>{label(c.a)}</th><td>{label(c.b)}</td><td>{fmt(c.rho,3)}</td></tr>)}</tbody></table></div></>:<p className="small-note">本次完整样本中，未发现数值因子 |ρ|≥0.70 的组合；这不排除其他依赖关系。</p>}<details><summary>查看每折留出的大样地与误差</summary><div className="table-scroll"><table><thead><tr><th>折</th><th>验证大样地</th><th>验证样方</th><th>模型 RMSE</th><th>基准 RMSE</th></tr></thead><tbody>{result.folds.map(f=><tr key={f.fold}><th>{f.fold}</th><td>{f.testBlocks.join('、')}</td><td>{f.n}</td><td>{fmt(f.rmse,3)}</td><td>{fmt(f.baselineRmse,3)}</td></tr>)}</tbody></table></div></details></Panel>
      <Panel title="方法与解释边界"><ul className="tree-notes">{result.notes.map(n=><li key={n}>{n}</li>)}</ul><div className="reference-links"><a href="https://scikit-learn.org/stable/modules/permutation_importance.html" target="_blank" rel="noreferrer">验证集置换重要性 ↗</a><a href="https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data" target="_blank" rel="noreferrer">分组交叉验证 ↗</a><a href="https://scikit-learn.org/stable/modules/partial_dependence.html" target="_blank" rel="noreferrer">偏依赖与相关因子的限制 ↗</a></div></Panel>
    </>}
  </>;
}

function ImportanceBars({result,label}:{result:ImportanceResult;label:(k:string)=>string}){
  const id=useId(),data=result.importance;
  const lo=Math.min(0,...data.map(r=>r.delta))*1.15,hi=Math.max(.001,...data.map(r=>r.delta))*1.12;
  const x=(v:number)=>205+(v-lo)/(hi-lo)*380,h=70+data.length*36;
  return <><div className="chart-tools"><span>{result.binary?'ΔBrier':'ΔMSE'} · 验证误差增量</span><ExportSVG id={id} name="环境因子-预测重要性"/></div><svg id={id} viewBox={`0 0 720 ${h}`} role="img" aria-label="环境因子验证集置换重要性排序图"><line x1={x(0)} y1="18" x2={x(0)} y2={h-38} stroke="#aebcb1"/>{data.map((r,i)=><g key={r.key}><text x="193" y={39+i*36} textAnchor="end">{label(r.key)}</text><rect x={Math.min(x(0),x(r.delta))} y={23+i*36} width={Math.max(1,Math.abs(x(r.delta)-x(0)))} height="22" rx="3" fill={r.delta>0?'#37765d':'#b5bcb1'}/><text x="600" y={39+i*36}>{r.share===null?'—':fmt(r.share,1)+'%'}<title>{label(r.key)}：误差增量 {fmt(r.delta,3)}，置换 SD {fmt(r.sd,3)}</title></text></g>)}{[lo,0,hi].map((v,i)=><text key={i} x={x(v)} y={h-12} textAnchor="middle">{fmt(v,1)}</text>)}</svg></>;
}
function DependencePlot({curve,name,response}:{curve:ImportanceResult['dependence'][number];name:string;response:string}){
  const id=useId(),points=curve.points;
  const ylo=Math.min(0,...points.map(p=>p.y)),yhi=Math.max(.01,...points.map(p=>p.y))*1.13;
  const y=(v:number)=>250-(v-ylo)/(yhi-ylo)*210;
  const xmin=Math.min(...points.map(p=>Number(p.x))),xmax=Math.max(...points.map(p=>Number(p.x)));
  const x=(v:number)=>68+(v-xmin)/(xmax-xmin||1)*440;
  return <><div className="chart-tools"><span>平均预测 · {response}</span><ExportSVG id={id} name={name+'-偏依赖'}/></div><svg id={id} viewBox="0 0 580 325" role="img" aria-label={name+'的偏依赖图'}>{Array.from({length:5},(_,i)=>ylo+(yhi-ylo)*i/4).map((v,i)=><g key={i}><line className="gridline" x1="68" x2="535" y1={y(v)} y2={y(v)}/><text x="56" y={y(v)+4} textAnchor="end">{fmt(v,1)}</text></g>)}{curve.categorical?points.map((p,i)=><g key={String(p.x)}><rect x={80+i*440/points.length} y={y(p.y)} width={Math.min(55,300/points.length)} height={250-y(p.y)} fill="#6d937d"/><text x={80+i*440/points.length} y="278">{String(p.x)}</text></g>):<><path d={points.map((p,i)=>`${i?'L':'M'}${x(Number(p.x))},${y(p.y)}`).join(' ')} stroke="#276c54" strokeWidth="3" fill="none"/>{[xmin,(xmin+xmax)/2,xmax].map((v,i)=><text key={i} x={x(v)} y="278" textAnchor="middle">{fmt(v,2)}</text>)}</>}<text x="295" y="312" textAnchor="middle">{name}</text></svg></>;
}
function PredictionPlot({result}:{result:ImportanceResult}){
  const id=useId(),max=Math.max(1,...result.predictions.flatMap(p=>[p.observed,p.predicted]))*1.08;
  const x=(v:number)=>65+v/max*440,y=(v:number)=>250-v/max*210;
  return <><div className="chart-tools"><span>留出预测 vs 原始观测</span><ExportSVG id={id} name="大样地-留出预测"/></div><svg id={id} viewBox="0 0 580 325" role="img" aria-label="按大样地交叉验证的观测与预测散点图">{Array.from({length:5},(_,i)=>max*i/4).map((v,i)=><g key={i}><line className="gridline" x1="65" x2="520" y1={y(v)} y2={y(v)}/><text x="53" y={y(v)+4} textAnchor="end">{fmt(v,1)}</text><text x={x(v)} y="278" textAnchor="middle">{fmt(v,1)}</text></g>)}<path d={`M65 250L${x(max)} ${y(max)}`} stroke="#9caf9e" strokeDasharray="5 5"/>{result.predictions.map(p=><circle key={p.plot} cx={x(p.observed)} cy={y(p.predicted)} r="4" fill="#386f57" fillOpacity=".62"><title>{p.plot}：观测 {fmt(p.observed)}，留出预测 {fmt(p.predicted)}</title></circle>)}<text x="285" y="313" textAnchor="middle">原始观测</text><text x="69" y="22">留出预测</text></svg></>;
}
