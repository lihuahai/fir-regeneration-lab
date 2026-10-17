"use client";
import { useId } from "react";
import type { Analysis, Column, Group, Model, Row } from "./types";

export const colors = ["#94ae86", "#277861", "#384d68"];
export const groupNames = ["低郁闭度", "中等郁闭度", "高郁闭度"];
export const fmt = (v: unknown, digits = 2): string => typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits }) : "—";
export const pv = (v: unknown): string => typeof v === "number" && Number.isFinite(v) ? v < .0001 ? "< 0.0001" : v.toFixed(4) : "—";
export function Legend() { return <div className="legend">{groupNames.map((g,i)=><span key={g}><i style={{background:colors[i]}}/>{g}</span>)}</div>; }
export function ExportSVG({id,name}:{id:string;name:string}) {
  return <button className="text-button export-chart" onClick={()=>{
    const svg=document.getElementById(id); if(!svg)return;
    const clone=svg.cloneNode(true) as SVGElement; clone.setAttribute("xmlns","http://www.w3.org/2000/svg");
    const style=document.createElementNS("http://www.w3.org/2000/svg","style"); style.textContent="text{font-family:Arial,'PingFang SC',sans-serif;fill:#52635d;font-size:12px}.gridline{stroke:#e7ece8;stroke-dasharray:3 4}.axis{stroke:#a5b3ab}.chart-label{font-size:13px;fill:#31473e}";clone.prepend(style);
    const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:"image/svg+xml"}));
    const a=document.createElement('a');a.href=url;a.download=name+'.svg';a.click();URL.revokeObjectURL(url);
  }}>导出 SVG <span aria-hidden>↗</span></button>;
}
export function BoxPlot({rows,groups,target,label}:{rows:Row[];groups:Group[];target:string;label:string}) {
  const id=useId(); const max=Math.max(1,...groups.map(g=>g.stats.max??0))*1.13;
  const y=(v:number)=>270-v/max*225;
  return <><div className="chart-tools"><span>{label}</span><ExportSVG id={id} name={label+'-组间分布'}/></div><svg id={id} viewBox="0 0 620 330" role="img" aria-label={label+'按郁闭度分组的箱线散点图'}>
    {Array.from({length:6},(_,i)=>max*i/5).map((t,i)=><g key={i}><line className="gridline" x1="58" y1={y(t)} x2="598" y2={y(t)}/><text x="47" y={y(t)+4} textAnchor="end">{fmt(t,t>10?0:1)}</text></g>)}
    {groups.map((g,i)=>{const s=g.stats;const x=145+i*180;if(s.n===0)return <text key={g.name} x={x} y="160" textAnchor="middle">无有效数据</text>;
      return <g key={g.name}><line x1={x} x2={x} y1={y(s.min!)} y2={y(s.max!)} stroke={colors[i]} strokeWidth="1.5"/>
        <line x1={x-18} x2={x+18} y1={y(s.min!)} y2={y(s.min!)} stroke={colors[i]}/><line x1={x-18} x2={x+18} y1={y(s.max!)} y2={y(s.max!)} stroke={colors[i]}/>
        <rect x={x-38} y={y(s.q3!)} width="76" height={Math.max(2,y(s.q1!)-y(s.q3!))} fill={colors[i]} fillOpacity=".15" stroke={colors[i]}/>
        <line x1={x-38} x2={x+38} y1={y(s.median!)} y2={y(s.median!)} stroke={colors[i]} strokeWidth="2.5"/>
        {rows.filter(r=>r.group===g.name&&typeof r[target]==='number').map((r,j)=><circle key={String(r.plot)} cx={x+((j*17)%57)-28} cy={y(Number(r[target]))} r="4" fill={colors[i]} fillOpacity=".68" stroke="white" strokeWidth=".6"><title>{String(r.plot)}：{fmt(r[target])}</title></circle>)}
        <text x={x} y="298" textAnchor="middle" className="chart-label">{g.name}</text><text x={x} y="318" textAnchor="middle">n = {s.n}</text></g>;
    })}
  </svg><p className="chart-foot">点为样方；箱体为第 25–75 百分位，中线为中位数，须为最小至最大值。</p></>;
}
export function StageBars({groups,heightDefinition,normalized=false}:{groups:Group[];heightDefinition:string;normalized?:boolean}) {
  const id=useId(); const values=groups.map(g=>g.stages.map(s=>normalized?(s.total??0)/(g.stages.reduce((a,x)=>a+(x.total??0),0)||1)*100:(s.mean??0)));
  const max=normalized?100:Math.max(1,...values.map(a=>a.reduce((s,v)=>s+v,0)))*1.15;
  const stageColors=['#2b775f','#9cb79d','#d1b77c'];
  return <><div className="chart-tools"><span>{normalized?'各级株数占组内总株数（%）':'各级平均株数 / 样方'}</span><ExportSVG id={id} name="更新级别结构"/></div><svg id={id} viewBox="0 0 430 280" role="img" aria-label="三个郁闭度组的更新级别组成">
    {values.map((vs,i)=>{let offset=0;return <g key={i}><text x="14" y={62+i*67} className="chart-label">{groupNames[i]}</text>{vs.map((v,j)=>{const x=117+offset/max*258;offset+=v;return <rect key={j} x={x} y={42+i*67} width={v/max*258} height="31" fill={stageColors[j]}><title>{groupNames[i]} {['I','II','III'][j]}级：{fmt(v)}{normalized?'%':' 株/样方'}</title></rect>;})}<text x={Math.min(395,123+offset/max*258)} y={62+i*67}>{fmt(offset,normalized?0:1)}</text></g>;})}
    {stageColors.map((c,i)=><g key={i}><rect x={125+i*87} y="251" width="10" height="10" rx="2" fill={c}/><text x={141+i*87} y="260">{['I','II','III'][i]} 级</text></g>)}
  </svg><p className="chart-foot">{heightDefinition}。级别组成不能解释为存活率或级间转化率。</p></>;
}
export function Scatter({rows,xKey,yKey,columns,curve}:{rows:Row[];xKey:string;yKey:string;columns:Column[];curve?:Model['curve']}) {
  const id=useId();const valid=rows.filter(r=>typeof r[xKey]==='number'&&typeof r[yKey]==='number');
  if(!valid.length)return <div className="empty">没有成对的有效观测。请检查缺失值与变量设置。</div>;
  const xs=valid.map(r=>Number(r[xKey])); const ys=valid.map(r=>Number(r[yKey]));
  let xmin=Math.min(...xs),xmax=Math.max(...xs);if(xmin===xmax){xmin-=1;xmax+=1;}
  const ymin=Math.min(0,...ys);const ymax=Math.max(1,...ys,...(curve??[]).map(c=>c.high).filter(Number.isFinite))*1.08;
  const sx=(x:number)=>64+(x-xmin)/(xmax-xmin)*500; const sy=(y:number)=>270-(Math.max(ymin,Math.min(ymax,y))-ymin)/(ymax-ymin)*226;
  const label=(k:string)=>columns.find(c=>c.key===k)?.label??k;
  const points=curve?.filter(c=>[c.y,c.low,c.high].every(Number.isFinite));
  return <><div className="chart-tools"><span>{label(yKey)}</span><ExportSVG id={id} name={label(xKey)+'-'+label(yKey)}/></div><svg id={id} viewBox="0 0 620 330" role="img" aria-label={label(xKey)+'与'+label(yKey)+'的散点图'}>
    {[0,1,2,3,4].map(i=>{const y=ymin+(ymax-ymin)*i/4;return <g key={i}><line className="gridline" x1="64" x2="564" y1={sy(y)} y2={sy(y)}/><text x="53" y={sy(y)+4} textAnchor="end">{fmt(y,ymax>10?0:1)}</text></g>;})}
    {[0,1,2,3,4,5].map(i=>{const x=xmin+(xmax-xmin)*i/5;return <text key={i} x={sx(x)} y="292" textAnchor="middle">{fmt(x,xmax>10?0:2)}</text>;})}
    {points&&points.length>1&&<><path d={'M'+points.map(c=>`${sx(c.x)},${sy(c.high)}`).join(' L')+' L'+[...points].reverse().map(c=>`${sx(c.x)},${sy(c.low)}`).join(' L')+' Z'} fill="#277861" opacity=".11"/><path d={'M'+points.map(c=>`${sx(c.x)},${sy(c.y)}`).join(' L')} fill="none" stroke="#277861" strokeWidth="2.5"/></>}
    {valid.map(r=><circle key={String(r.plot)} cx={sx(Number(r[xKey]))} cy={sy(Number(r[yKey]))} r="4.8" fill={colors[groupNames.indexOf(String(r.group))]??'#999'} opacity=".75" stroke="white" strokeWidth="1"><title>{String(r.plot)} · {String(r.group)}\n{label(xKey)}：{fmt(r[xKey])}\n{label(yKey)}：{fmt(r[yKey])}</title></circle>)}
    <text x="314" y="321" textAnchor="middle" className="chart-label">{label(xKey)}{columns.find(c=>c.key===xKey)?.unit==='%'?'（%）':''}</text>
  </svg></>;
}
export function PcaPlot({analysis}:{analysis:Analysis}){
  const id=useId();const p=analysis.pca;if(p.error)return <div className="empty">{p.error}</div>;
  const pts=p.points!; const maxX=Math.max(1,...pts.map(x=>Math.abs(x.x)))*1.18,maxY=Math.max(1,...pts.map(x=>Math.abs(x.y)))*1.18;
  const sx=(v:number)=>310+v/maxX*245,sy=(v:number)=>175-v/maxY*130;
  return <><div className="chart-tools"><span>环境梯度 · 标准化 PCA</span><ExportSVG id={id} name="环境PCA"/></div><svg id={id} viewBox="0 0 620 350" role="img" aria-label="环境因子主成分分析样方分布">
    <line x1="55" y1="175" x2="565" y2="175" className="gridline"/><line x1="310" y1="35" x2="310" y2="305" className="gridline"/>
    {[-1,-.5,0,.5,1].map(t=><g key={t}><text x={sx(maxX*t)} y="325" textAnchor="middle">{fmt(maxX*t,1)}</text><text x="44" y={sy(maxY*t)+4} textAnchor="end">{fmt(maxY*t,1)}</text></g>)}
    {pts.map(r=><circle key={r.plot} cx={sx(r.x)} cy={sy(r.y)} r="5.5" fill={colors[groupNames.indexOf(r.group)]??'#999'} fillOpacity=".75" stroke="white"><title>{r.plot} · {r.group}\nPC1 {fmt(r.x)} · PC2 {fmt(r.y)}</title></circle>)}
    <text x="310" y="347" textAnchor="middle">PC1 · {fmt(p.variance![0]*100,1)}%</text><text transform="translate(15 180) rotate(-90)" textAnchor="middle">PC2 · {fmt(p.variance![1]*100,1)}%</text>
  </svg></>;
}
