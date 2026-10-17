"""Reproducible plot-level exploratory analyses. Source observations are never changed."""
import hashlib
import io
import csv
import json
import math
import re
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np
import openpyxl
from scipy import stats
from statsmodels.stats.multitest import multipletests
import statsmodels.api as sm
from statsmodels.discrete.discrete_model import NegativeBinomial

SEED = 20261017
B = 4999
# Height classes confirmed by the user; these are independent of canopy thresholds.
HEIGHT_BOUNDS = (20.0, 40.0)


def height_definition():
    if HEIGHT_BOUNDS is None:
        return "高度级边界待补充，I–III 级标签暂沿用原始记录"
    low, high = HEIGHT_BOUNDS
    return f"高度级：I 级 0<H≤{low:g} cm；II 级 {low:g}<H≤{high:g} cm；III 级 H>{high:g} cm"


KNOWN = [
    ("plot", "样方编号", "id", ""), ("canopy", "郁闭度", "environment", "%"),
    ("n1", "I 级株数", "count", "株/样方"), ("d1", "I 级平均地径 (cm)", "trait", "cm"),
    ("h1", "I 级平均高 (cm)", "trait", "cm"), ("n2", "II 级株数", "count", "株/样方"),
    ("d2", "II 级平均地径 (cm)", "trait", "cm"), ("h2", "II 级平均高 (cm)", "trait", "cm"),
    ("n3", "III 级株数", "count", "株/样方"), ("d3", "III 级平均地径 (cm)", "trait", "cm"),
    ("h3", "III 级平均高 (cm)", "trait", "cm"),
    ("litter", "枯枝落叶层平均值", "environment", "单位待确认"),
    ("treeDensity", "乔木平均密度", "environment", "单位待确认"),
    ("adult", "冷杉数（胸径≥5cm）", "environment", "株/样方"),
    ("shrubHeight", "灌木层平均高", "environment", "单位待确认"),
    ("shrubDensity", "灌木层平均密度", "environment", "单位待确认"),
]
GROUPS = ["低郁闭度", "中等郁闭度", "高郁闭度"]


def clean(v):
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [clean(x) for x in v]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def num(v):
    if v is None or isinstance(v, bool) or str(v).strip() in ("", "NA", "N/A", "—", "-"):
        return None
    try:
        f = float(str(v).strip().replace(",", ""))
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def norm(s):
    return str(s).strip().replace(" ", "").replace("（", "(").replace("）", ")")


def column(label):
    if norm(label) in ("样方", "样方编号"):
        return dict(key="plot", label="样方编号", role="id", unit="")
    for k, l, role, unit in KNOWN:
        if norm(label) == norm(l) or label == k:
            return dict(key=k, label=l, role=role, unit=unit)
    k = "v_" + hashlib.sha1(str(label).encode()).hexdigest()[:10]
    return dict(key=k, label=str(label).strip(), role="environment", unit="原始单位")


def parse_table(matrix, name="数据", sheet="Sheet1"):
    if not matrix:
        raise ValueError("数据为空。请保留首行变量名称。")
    headers = matrix[0]
    id_indices = [i for i, h in enumerate(headers) if h is not None and norm(h) in ("样方编号", "样方")]
    if not id_indices:
        raise ValueError("未找到‘样方编号’列。首行应为表头，每行代表一个样方。")
    records, columns, issues, provenance = {}, {}, [], {}
    for segment, start in enumerate(id_indices):
        end = id_indices[segment + 1] if segment + 1 < len(id_indices) else len(headers)
        mapping = {}
        for i in range(start, end):
            label = headers[i]
            if label is None or not str(label).strip() or ("郁闭度" in str(label) and any(x in str(label) for x in ("低", "中等", "高等", "高郁"))):
                continue
            c = column(label)
            if c["key"] in [x["key"] for x in mapping.values()]:
                raise ValueError(f"存在重复表头：{label}。请为每个变量使用唯一名称。")
            mapping[i] = c
            columns[c["key"]] = c
        seen = set()
        for ri, vals in enumerate(matrix[1:], 2):
            pid = vals[start] if start < len(vals) else None
            if pid is None or not str(pid).strip() or norm(pid) in ("样方", "样方编号"):
                continue
            pid = str(pid).strip()
            if pid in seen:
                raise ValueError(f"第 {segment+1} 块数据中样方 {pid} 重复（第 {ri} 行），请先核对编号。")
            seen.add(pid)
            r = records.setdefault(pid, {"plot": pid})
            provenance.setdefault(pid, []).append({"block": segment+1, "row": ri})
            for i, c in mapping.items():
                if c["key"] != "plot":
                    r[c["key"]] = vals[i] if i < len(vals) else None
        if segment == 0:
            left = set(seen)
        elif seen != left:
            issues.append(f"左右数据按编号合并，编号覆盖不一致：仅左侧 {', '.join(sorted(left-seen)) or '无'}；仅右侧 {', '.join(sorted(seen-left)) or '无'}。未匹配值保留缺失。")
    cols = list(columns.values())
    for c in cols:
        values = [r.get(c["key"]) for r in records.values() if r.get(c["key"]) not in (None, "")]
        if c["key"].startswith("v_") and values and sum(num(v) is not None for v in values) < len(values)*0.8:
            c["role"] = "label"
    return dict(name=name, sheet=sheet, columns=cols, rows=list(records.values()), importIssues=issues, provenance=provenance,
                layout="按样方编号连接左右两表" if len(id_indices)>1 else "一行一个样方")


def read_file(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        raw = p.read_bytes()
        try:
            s = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            s = raw.decode("gb18030")
        return parse_table(list(csv.reader(io.StringIO(s))), p.name, "CSV")
    book = openpyxl.load_workbook(p, data_only=True, read_only=True)
    try:
        sheet = book.worksheets[0]
        return parse_table(list(sheet.values), p.name, sheet.title)
    finally:
        book.close()


def prepared(dataset, config):
    cols = [dict(c) for c in dataset["columns"]]
    roles = config.get("roles", {})
    for c in cols:
        c["role"] = roles.get(c["key"], c["role"])
        if c['key'] == config.get('areaColumn'):
            c['role'] = 'area'
    rows, issues = [], list(dataset.get("importIssues", []))
    structural = 0
    low, high = float(config.get("low", 30)), float(config.get("high", 70))
    if not 0 <= low < high <= 100:
        raise ValueError("郁闭度阈值需要满足 0 ≤ 低值 < 高值 ≤ 100。")
    ids = set()
    for source in dataset["rows"]:
        r = dict(source)
        pid = str(r.get("plot", "")).strip()
        if not pid or pid in ids:
            raise ValueError(f"样方编号为空或重复：{pid or '(空)'}")
        ids.add(pid)
        r["plot"] = pid
        for c in cols:
            k = c["key"]
            if c["role"] not in ("id", "label"):
                original = r.get(k)
                r[k] = num(original)
                if original not in (None, "") and r[k] is None:
                    issues.append(f"{pid} / {c['label']}：非有效数值，分析时视为缺失。")
        for k in ("n1", "n2", "n3"):
            v = num(r.get(k))
            if v is not None and (v < 0 or v != int(v)):
                issues.append(f"{pid} / {k}：株数须为非负整数，当前值 {v} 已排除。")
                v = None
            r[k] = v
        for j in (1, 2, 3):
            n = r.get(f"n{j}")
            for trait in (f"d{j}", f"h{j}"):
                val = num(r.get(trait))
                if n is None or n == 0:
                    if n == 0 and val is not None:
                        structural += 1
                        if val != 0:
                            issues.append(f"{pid} / {trait}：株数为 0 但形态值非 0，已排除形态值。")
                    r[trait] = None
                elif val is not None and val <= 0:
                    issues.append(f"{pid} / {trait}：有植株但形态均值不大于 0，已排除。")
                    r[trait] = None
                else:
                    r[trait] = val
            height = r.get(f'h{j}')
            bounds = HEIGHT_BOUNDS
            if height is not None and bounds is not None and not ((j == 1 and height <= bounds[0]) or (j == 2 and bounds[0] < height <= bounds[1]) or (j == 3 and height > bounds[1])):
                issues.append(f"{pid} / h{j}：平均高度 {height} cm 与已确认的高度级边界不符，请核对原始记录；当前保留原值，不自动重分类。")
        counts = [r.get(k) for k in ("n1", "n2", "n3")]
        r["total"] = sum(counts) if all(v is not None for v in counts) else None
        r["presence"] = float(r["total"] > 0) if r["total"] is not None else None
        r["laterShare"] = (r["n2"]+r["n3"])/r["total"]*100 if r["total"] is not None and r["total"]>0 else None
        c = num(r.get("canopy"))
        if c is not None and not 0 <= c <= 100:
            issues.append(f"{pid}：郁闭度 {c} 不在 0–100 范围，已排除该郁闭度。")
            c = None
        r["canopy"] = c
        r["group"] = GROUPS[0 if c <= low else 1 if c <= high else 2] if c is not None else "郁闭度缺失"
        parts = re.split(r'\s*[-—–－]+\s*', pid)
        r["block"] = parts[0] if len(parts) > 1 else pid
        area_key = config.get("areaColumn")
        area = num(r.get(area_key)) if area_key else num(config.get("area"))
        r["area"] = area if area and area > 0 else None
        r["density"] = r["total"] / area * 100 if area and area>0 and r["total"] is not None else None
        rows.append(r)
    extra = [dict(key="total",label="更新总株数",role="derived",unit="株/样方"),
             dict(key="presence",label="更新出现",role="derived",unit="0/1"),
             dict(key="laterShare",label="II、III 级占比",role="derived",unit="%"),
             dict(key="density",label="更新密度",role="derived",unit="株/100 m²")]
    missing = [{"key":c["key"],"label":c["label"],"n":sum(r.get(c["key"]) is None for r in rows)} for c in cols if c["role"] not in ("label","id")]
    return rows, cols+extra, dict(issues=issues, structural=structural, missing=missing,
                                heightConflicts=sum('与已确认的高度级边界不符' in issue for issue in issues),
                                unmatchedCanopy=sum(r["group"]=="郁闭度缺失" for r in rows))


def summary(values):
    x = np.array([v for v in values if v is not None], dtype=float)
    if not len(x):
        return dict(n=0, mean=None, median=None, sd=None, q1=None, q3=None, min=None, max=None, total=None)
    return dict(n=len(x), mean=x.mean(), median=np.median(x), sd=x.std(ddof=1) if len(x)>1 else None,
                q1=np.quantile(x,.25), q3=np.quantile(x,.75), min=x.min(), max=x.max(), total=x.sum())


def wilson(k, n):
    if not n:
        return [None,None]
    z=1.95996398454
    center=(k/n+z*z/(2*n))/(1+z*z/n)
    half=z*math.sqrt(k/n*(1-k/n)/n+z*z/(4*n*n))/(1+z*z/n)
    return [center-half,center+half]


@lru_cache(maxsize=4)
def permutation_indices(blocks):
    """Each row is a uniform permutation within each original sampling block."""
    blocks = np.asarray(blocks)
    out = np.tile(np.arange(len(blocks)), (B, 1))
    rng = np.random.default_rng(SEED)
    for block in dict.fromkeys(blocks):
        ix = np.flatnonzero(blocks == block)
        out[:, ix] = rng.permuted(np.tile(ix, (B, 1)), axis=1)
    return out


def cluster_occupancy_ci(rows):
    blocks = list(dict.fromkeys(r['block'] for r in rows))
    occupied = sum(r['total'] > 0 for r in rows)
    if len(blocks) < 5 or occupied in (0, len(rows)):
        return [None, None]
    counts = np.array([[sum(r['total'] > 0 for r in rows if r['block'] == b),
                        sum(r['block'] == b for r in rows)] for b in blocks])
    draws = np.random.default_rng(SEED).integers(0, len(blocks), size=(B, len(blocks)))
    totals = counts[draws].sum(axis=1)
    return np.quantile(totals[:, 0] / totals[:, 1], [.025, .975])


def group_test(rows, key):
    selected = [r for g in GROUPS for r in rows if r['group'] == g and r.get(key) is not None]
    gs = [[r[key] for r in selected if r["group"]==g] for g in GROUPS]
    active = [(GROUPS[i], np.array(v,dtype=float)) for i,v in enumerate(gs) if len(v)]
    if len(active)<2:
        return dict(error="至少需要两个有有效观测的郁闭度组。", pairs=[])
    x=np.concatenate([a[1] for a in active]); n=len(x); sizes=np.array([len(a[1]) for a in active]); k=len(active)
    if len(np.unique(x))<2:
        return dict(error="所有有效观测相同，无法检验差异。", pairs=[])
    h, pa = stats.kruskal(*[a[1] for a in active])
    rank=stats.rankdata(x); tie=stats.tiecorrect(rank)
    blocks = tuple(r['block'] for r in selected)
    labels = np.array([r['group'] for r in selected])
    informative = sum(len(set(labels[np.array(blocks) == b])) > 1 for b in set(blocks))
    if not informative:
        return dict(error="各大样地内没有跨郁闭度组的有效观测，不能进行大样地内比较。", pairs=[], h=h, n=n)
    perms=rank[permutation_indices(blocks)]
    bounds=np.r_[0,np.cumsum(sizes)]
    sums=np.column_stack([perms[:,bounds[j]:bounds[j+1]].sum(axis=1) for j in range(k)])
    hs=(12/(n*(n+1))*(sums*sums/sizes).sum(axis=1)-3*(n+1))/tie
    p=(1+np.sum(hs>=h-1e-10))/(B+1)
    pairs=[]
    for a in range(k):
        for b in range(a+1,k):
            pair = [r for r in selected if r['group'] in (active[a][0], active[b][0])]
            pb = tuple(r['block'] for r in pair)
            mask = np.array([r['group'] == active[a][0] for r in pair])
            mixed = sum(len(set(mask[np.array(pb) == q])) > 1 for q in set(pb))
            pr = stats.rankdata([r[key] for r in pair])
            # Remove fixed block means before the rank contrast; permutation keeps them fixed.
            for q in set(pb):
                ix = np.array(pb) == q
                pr[ix] -= pr[ix].mean()
            contrast = abs(pr[mask].mean() - pr[~mask].mean())
            perm = pr[permutation_indices(pb)]
            null = abs(perm[:, mask].mean(axis=1) - perm[:, ~mask].mean(axis=1))
            pairs.append(dict(a=active[a][0], b=active[b][0], contrast=contrast, blocks=mixed,
                              p=(1+np.sum(null >= contrast-1e-12))/(B+1) if mixed else None, adjusted=None))
    valid_pairs = [v for v in pairs if v['p'] is not None]
    if valid_pairs:
        for item,padj in zip(valid_pairs,multipletests([v['p'] for v in valid_pairs],method='holm')[1]):
            item['adjusted']=padj
    return dict(h=h,p=p,asymptoticP=pa,n=n,epsilon2=max(0,(h-k+1)/(n-k)) if n>k else None,
                method="Kruskal–Wallis H；大样地内 4,999 次受限置换；两两秩差受限置换 + Holm",pairs=pairs,
                blocks=len(set(blocks)), informativeBlocks=informative,
                small=any(s<5 for s in sizes))


def correlations(rows, envs, targets, blocked=True):
    output=[]
    for a in envs:
        for b in targets:
            if a==b:
                continue
            complete=[r for r in rows if r.get(a) is not None and r.get(b) is not None]
            pairs=[(r[a],r[b]) for r in complete]
            blocks=tuple(r['block'] if blocked else 'all' for r in complete)
            item=dict(x=a,y=b,n=len(pairs),blocks=len(set(blocks)),rho=None,pooledRho=None,p=None,q=None)
            if len(pairs)>=4:
                xy=np.array(pairs,float); rx=stats.rankdata(xy[:,0]); ry=stats.rankdata(xy[:,1]); rx-=rx.mean(); ry-=ry.mean()
                denom=np.linalg.norm(rx)*np.linalg.norm(ry)
                if denom>0:
                    item['pooledRho'] = float(rx@ry/denom)
                    if blocked:
                        for block in set(blocks):
                            ix = np.array(blocks) == block
                            rx[ix] -= rx[ix].mean(); ry[ix] -= ry[ix].mean()
                    denom=np.linalg.norm(rx)*np.linalg.norm(ry)
                if denom>1e-12:
                    rho=float(rx@ry/denom)
                    perm=ry[permutation_indices(blocks)]
                    null=(perm@rx)/denom
                    item.update(rho=rho,p=(1+np.sum(abs(null)>=abs(rho)-1e-12))/(B+1))
            output.append(item)
    valid=[o for o in output if o['p'] is not None]
    if valid:
        for item,q in zip(valid,multipletests([o['p'] for o in valid],method='fdr_bh')[1]): item['q']=q
    return output


def pca(rows, envs):
    usable=[k for k in envs if len({r.get(k) for r in rows if r.get(k) is not None})>1]
    complete=[r for r in rows if all(r.get(k) is not None for k in usable)]
    if len(usable)<2 or len(complete)<max(5,len(usable)+1):
        return dict(error="PCA 需要至少 2 个非恒定环境变量，以及足够的完整样方。可在变量设置中排除缺失较多的列。")
    x=np.array([[r[k] for k in usable] for r in complete],float)
    sd=x.std(axis=0,ddof=1); good=sd>1e-12
    x=x[:,good]; usable=[k for k,g in zip(usable,good) if g]
    if len(usable)<2:
        return dict(error="完整样方中的非恒定环境变量不足 2 个。")
    z=(x-x.mean(axis=0))/x.std(axis=0,ddof=1)
    u,s,vt=np.linalg.svd(z,full_matrices=False)
    for j in range(2):
        sign=1 if vt[j,np.argmax(abs(vt[j]))]>=0 else -1
        u[:,j]*=sign; vt[j,:]*=sign
    scores=u[:,:2]*s[:2]
    return dict(n=len(complete),excluded=len(rows)-len(complete),variance=(s*s/(s*s).sum())[:2],
                points=[dict(plot=r['plot'],group=r['group'],x=xy[0],y=xy[1]) for r,xy in zip(complete,scores)],
                loadings=[dict(key=k,x=vt[0,i],y=vt[1,i]) for i,k in enumerate(usable)])


def fit_model(rows, cols, config, target):
    envs=[c['key'] for c in cols if c['role']=='environment']
    predictors=[k for k in config.get('predictors',['canopy','litter']) if k in envs and k!=target]
    if not predictors:
        return dict(error="请选择至少一个环境因子。")
    if len(predictors)>3:
        return dict(error="为控制小样本过拟合，最多选择 3 个环境因子。")
    use_area=bool(config.get('areaColumn') or num(config.get('area')))
    complete=[r for r in rows if all(r.get(k) is not None for k in [target]+predictors) and (not use_area or r.get('area'))]
    n=len(complete)
    quadratic=bool(config.get('quadratic',True)) and 'canopy' in predictors
    terms=predictors+(['canopySquared'] if quadratic else [])
    if n<max(15,(len(terms)+1)*4):
        return dict(error=f"有效样方仅 {n} 个，当前模型至少需要 {max(15,(len(terms)+1)*4)} 个。请减少变量或补齐数据。")
    y=np.array([r[target] for r in complete],float)
    count=target in ('total','n1','n2','n3') or next((c['role']=='count' for c in cols if c['key']==target),False)
    if not count:
        return dict(error="当前回归针对更新株数。请将响应指标切换为总株数或 I、II、III 级株数；形态指标可用组间比较和相关分析。")
    if np.any(y<0) or np.any(y!=np.floor(y)) or np.std(y)<1e-10:
        return dict(error="计数回归需要有变异的非负整数响应变量。")
    raw=np.array([[r[k] for k in predictors] for r in complete],float)
    means=raw.mean(axis=0); stds=raw.std(axis=0,ddof=1)
    if np.any(stds<1e-10):
        return dict(error="所选环境变量含恒定列，请取消该变量。")
    z=(raw-means)/stds
    design=np.c_[np.ones(n),z]
    if quadratic: design=np.c_[design,z[:,predictors.index('canopy')]**2]
    if np.linalg.matrix_rank(design)<design.shape[1]:
        return dict(error="环境变量完全共线，无法估计模型。请减少重复变量。")
    offset=np.log([r['area'] for r in complete]) if use_area else None
    cluster=config.get('cluster','prefix')=='prefix'
    blocks=np.array([r['block'] for r in complete]); nblocks=len(set(blocks))
    if cluster and nblocks<5:
        return dict(error="按编号前缀聚类后不足 5 个簇，无法提供可靠的聚类标准误。")
    covariance=dict(cov_type='cluster',cov_kwds={'groups':blocks,'use_correction':True}) if cluster else dict(cov_type='HC0')
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        try:
            poisson=sm.GLM(y,design,family=sm.families.Poisson(),offset=offset).fit(**covariance)
            dispersion=float(np.sum(poisson.resid_pearson**2)/poisson.df_resid)
            family=config.get('family','auto')
            choose_nb=family=='nb' or (family=='auto' and dispersion>1.5)
            if choose_nb:
                result=NegativeBinomial(y,design,offset=offset,loglike_method='nb2').fit(disp=0,maxiter=500,**covariance)
                if not result.mle_retvals.get('converged',False):
                    return dict(error="负二项模型未收敛，请减少变量或改用 Poisson 作敏感性比较；未输出不稳定系数。")
                model_name='负二项回归（NB2）'
                alpha=float(result.params[-1])
            else:
                result=poisson; model_name='Poisson 回归'; alpha=None
            cov=np.array(result.cov_params())[:design.shape[1],:design.shape[1]]
            params=np.array(result.params)[:design.shape[1]]
            if not np.all(np.isfinite(cov)) or np.any(np.diag(cov)<0):
                return dict(error="模型协方差不可估计，未输出系数。请减少变量。")
            se=np.sqrt(np.diag(cov)); critical=stats.t.ppf(.975,nblocks-1) if cluster else stats.norm.ppf(.975)
            pvalues=2*stats.t.sf(abs(params/se),nblocks-1) if cluster else 2*stats.norm.sf(abs(params/se))
            coefficients=[dict(key=k,beta=b,se=e,p=p,irr=np.exp(b),low=np.exp(b-critical*e),high=np.exp(b+critical*e)) for k,b,e,p in zip(['intercept']+terms,params,se,pvalues)]
            vifs=[]
            for j,k in enumerate(predictors):
                fit=sm.OLS(z[:,j],np.delete(design,j+1,axis=1)).fit()
                vifs.append(dict(key=k,value=1/(1-fit.rsquared) if fit.rsquared<1 else None))
            axis='canopy' if 'canopy' in predictors else predictors[0]
            ix=predictors.index(axis); grid=np.linspace(raw[:,ix].min(),raw[:,ix].max(),70)
            gx=np.zeros((len(grid),len(predictors))); gx[:,ix]=(grid-means[ix])/stds[ix]
            gd=np.c_[np.ones(len(grid)),gx]
            if quadratic: gd=np.c_[gd,gx[:,predictors.index('canopy')]**2]
            exposure=float(np.median([r['area'] for r in complete])) if use_area else 1
            eta=gd@params+math.log(exposure); se_pred=np.sqrt(np.maximum(0,np.einsum('ij,jk,ik->i',gd,cov,gd)))
            curve=[dict(x=x,y=np.exp(e),low=np.exp(e-critical*s),high=np.exp(e+critical*s)) for x,e,s in zip(grid,eta,se_pred)]
            aic=float(result.aic); k=len(result.params)
            fitted=np.exp(design@params+(offset if offset is not None else 0))
            predzero=np.mean((1+alpha*fitted)**(-1/alpha)) if alpha is not None and alpha>0 else np.mean(np.exp(-fitted))
            notes=["已确认同一编号前缀的小样方属于同一大样地；" + height_definition() + "。样方面积仍待补充。",
                   "计数模型关联不代表因果效应；未控制的地形、土壤、种源与空间位置可能混杂。"]
            if cluster: notes.append(f"按 {nblocks} 个大样地聚类，使用小样本修正与 t({nblocks-1}) 区间。大样地数较少，推断仍为探索性；稳健标准误不等于控制大样地的全部混杂。")
            if not use_area: notes.append("未校正样方面积，比较单位为株/样方。只有等面积样方才可直接比较丰度强弱。")
            if any(v['value'] is None or v['value']>5 for v in vifs): notes.append("存在 VIF > 5 的共线性信号，单个系数解释需谨慎。")
            if quadratic: notes.append("郁闭度同时含一次项和二次项，应联合阅读响应曲线，不能把一次项 IRR 解释为整个梯度的固定效应。")
            if caught: notes.append("拟合产生数值提示："+'；'.join(sorted({str(w.message) for w in caught}))[:500])
            return dict(name=model_name,n=n,excluded=len(rows)-n,predictors=predictors,quadratic=quadratic,
                        dispersion=dispersion,alpha=alpha,aic=aic,aicc=aic+2*k*(k+1)/(n-k-1) if n>k+1 else None,
                        poissonAic=poisson.aic,coefficients=coefficients,vifs=vifs,curve=curve,axis=axis,
                        covariance=f"按编号前缀聚类，{nblocks} 簇" if cluster else "HC0 稳健标准误（假定样方独立）",
                        observedZero=np.mean(y==0),expectedZero=predzero,notes=notes,exposure=exposure,
                        scales=[dict(key=k,mean=m,sd=s) for k,m,s in zip(predictors,means,stds)])
        except (ValueError,RuntimeError,np.linalg.LinAlgError,OverflowError,ZeroDivisionError) as e:
            return dict(error=f"模型无法稳定估计：{str(e)[:180]}。请减少变量或检查数据。")


def analyze(dataset, config=None):
    config=config or {}
    rows,cols,audit=prepared(dataset,config)
    target=config.get('target','total')
    allowed={c['key'] for c in cols if c['role'] not in ('label','id')}
    if target not in allowed: raise ValueError("响应指标已不存在，请重新选择。")
    envs=[c['key'] for c in cols if c['role']=='environment' and c['key']!=target]
    grouped=[]
    for g in GROUPS:
        rs=[r for r in rows if r['group']==g]
        valid=[r for r in rs if r['total'] is not None]
        occupied=sum(r['total']>0 for r in valid)
        grouped.append(dict(name=g,n=len(rs),stats=summary([r.get(target) for r in rs]),
                            total=summary([r['total'] for r in rs]),occupied=occupied,occupancy=occupied/len(valid) if valid else None,
                            occupancyCI=cluster_occupancy_ci(valid),validTotal=len(valid),blocks=len({r['block'] for r in rs}),
                            stages=[summary([r[k] for r in rs]) for k in ('n1','n2','n3')],
                            traits=[dict(key=k,stats=summary([r.get(k) for r in rs])) for k in ('h1','h2','h3','d1','d2','d3')]))
    valid=[r for r in rows if r['total'] is not None]
    targets=list(dict.fromkeys(['total','n1','n2','n3']+([target] if target not in ('total','n1','n2','n3') else [])))
    screen=[]
    for k in envs:
        test=group_test(rows,k) if k!='canopy' else {}
        h,p=test.get('h'),test.get('p')
        screen.append(dict(key=k,h=h,p=p,q=None,groups=[summary([r.get(k) for r in rows if r['group']==g]) for g in GROUPS]))
    tests=[s for s in screen if s['p'] is not None and np.isfinite(s['p']) and s['key']!='canopy']
    if tests:
        for item,q in zip(tests,multipletests([s['p'] for s in tests],method='fdr_bh')[1]): item['q']=q
    for s in screen:
        if s['key']=='canopy': s.update(p=None,q=None,h=None)
    result=dict(rows=rows,columns=cols,audit=audit,groups=grouped,groupTest=group_test(rows,target),
                heightDefinition=height_definition(),heightConfirmed=HEIGHT_BOUNDS is not None,
                correlations=correlations(rows,envs,targets),pca=pca(rows,envs),environmentScreen=screen,
                model=fit_model(rows,cols,config,target),target=target,seed=SEED,permutations=B,
                overview=dict(n=len(rows),total=sum(r['total'] for r in valid),validTotal=len(valid),
                              occupied=sum(r['total']>0 for r in valid),zeros=sum(r['total']==0 for r in valid),
                              envCount=len(envs),blocks=len({r['block'] for r in rows}),
                              stages=[summary([r[k] for r in rows]) for k in ('n1','n2','n3')]))
    return clean(result)
