"""Grouped out-of-sample prediction and permutation importance; no causal attribution."""
import math
import warnings

import numpy as np
from scipy.stats import spearmanr
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (RandomForestRegressor, ExtraTreesRegressor, GradientBoostingRegressor,
                              RandomForestClassifier, ExtraTreesClassifier, GradientBoostingClassifier)
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from engine import SEED, clean, prepared

REPEATS = 20
TREES = 160
METHODS = {'rf': '随机森林', 'extra': '极端随机树', 'boost': '梯度提升树'}
OUTCOMES = {'n1', 'n2', 'n3', 'h1', 'h2', 'h3', 'd1', 'd2', 'd3',
            'total', 'presence', 'laterShare', 'density'}


def group_splits(groups):
    """Entire big plots stay on one side of each validation split."""
    nfolds = min(4, len(set(groups)))
    return list(GroupKFold(n_splits=nfolds).split(np.zeros(len(groups)), groups=groups))


def fit_importance(dataset, config=None, progress=None):
    config = config or {}
    notify = progress or (lambda text: None)
    rows, columns, _ = prepared(dataset, config)
    target = config.get('target', 'total')
    if target not in {c['key'] for c in columns if c['role'] in ('count', 'trait', 'derived')}:
        raise ValueError('请选择株数、形态、级别占比或更新出现作为响应指标。')
    eligible = {c['key']: c for c in columns if c['role'] in ('environment', 'categorical')
                and c['key'] not in OUTCOMES and c['key'] != config.get('areaColumn')}
    requested = config.get('mlPredictors', list(eligible))
    if not requested or len(requested) > 20 or len(requested) != len(set(requested)) or any(k not in eligible for k in requested):
        raise ValueError('请勾选 1–20 个环境因子；株数、形态响应和面积列不能作为预测因子。')
    method = config.get('mlMethod', 'rf')
    if method not in METHODS:
        raise ValueError('不支持的树模型，请重新选择。')
    categorical = {k for k in requested if eligible[k]['role'] == 'categorical'}
    complete = [r for r in rows if r.get(target) is not None and all(
        r.get(k) is not None and (k not in categorical or str(r[k]).strip()) for k in requested)]
    n = len(complete)
    groups = np.array([r['block'] for r in complete])
    nblocks = len(set(groups))
    if n < 24 or nblocks < 6:
        raise ValueError(f'完整样本仅 {n} 个、{nblocks} 个大样地；至少需要 24 个样方、6 个大样地。请减少缺失较多的变量或补充数据。')
    keys = [k for k in requested if len({r[k] for r in complete}) > 1]
    dropped = [k for k in requested if k not in keys]
    if not keys:
        raise ValueError('所选环境因子均无变异，不能训练模型。')
    if any(len({str(r[k]) for r in complete}) > 20 for k in keys if k in categorical):
        raise ValueError('分类因子超过 20 类，请核对变量用途，不要用样方编号作预测因子。')
    x = np.array([[str(r[k]).strip() if k in categorical else float(r[k]) for k in keys] for r in complete], dtype=object)
    y = np.array([float(r[target]) for r in complete])
    if np.ptp(y) == 0:
        raise ValueError('响应指标没有变异，无法比较预测能力或因子重要性。')
    binary = target == 'presence'
    numeric_idx = [j for j, k in enumerate(keys) if k not in categorical]
    cat_idx = [j for j, k in enumerate(keys) if k in categorical]
    params = dict(n_estimators=TREES, max_depth=6, min_samples_leaf=3, max_features=0.7,
                  random_state=SEED, n_jobs=1)

    def create_model():
        transforms = []
        if numeric_idx:
            transforms.append(('numeric', 'passthrough', numeric_idx))
        if cat_idx:
            transforms.append(('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), cat_idx))
        if method == 'boost':
            cls = GradientBoostingClassifier if binary else GradientBoostingRegressor
            estimator = cls(n_estimators=120, learning_rate=0.03, max_depth=2,
                            min_samples_leaf=4, random_state=SEED)
        else:
            cls = ((RandomForestClassifier if binary else RandomForestRegressor) if method == 'rf'
                   else (ExtraTreesClassifier if binary else ExtraTreesRegressor))
            estimator = cls(**params)
        return make_pipeline(ColumnTransformer(transforms), estimator)

    def predict(model, data):
        if binary:
            return model.predict_proba(data)[:, 1]
        pred = model.predict(data)
        # All supported ecological responses are nonnegative; shares have a known upper bound.
        return np.clip(pred, 0, 100 if target == 'laterShare' else None)

    splits = group_splits(groups)
    nf = len(splits)
    predictions, baseline = np.zeros(n), np.zeros(n)
    deltas = np.zeros((nf, len(keys), REPEATS))
    folds, fold_weights = [], []
    for fi, (train, test) in enumerate(splits):
        notify(f'{METHODS[method]}：大样地交叉验证 {fi+1}/{nf}…')
        if binary and len(np.unique(y[train])) < 2:
            raise ValueError('某训练折只有一种更新状态，无法拟合分类模型。请补充大样地或改用株数指标。')
        model = create_model()
        model.fit(x[train], y[train])
        pred = predict(model, x[test])
        predictions[test] = pred
        baseline[test] = y[train].mean()
        errors = (y[test] - pred)**2
        rng = np.random.default_rng(SEED + fi)
        for j in range(len(keys)):
            shuffled = np.tile(x[test], (REPEATS, 1))
            for rep in range(REPEATS):
                shuffled[rep*len(test):(rep+1)*len(test), j] = x[test][rng.permutation(len(test)), j]
            permuted = predict(model, shuffled).reshape(REPEATS, len(test))
            deltas[fi, j] = np.mean((y[test][None, :] - permuted)**2, axis=1) - errors.mean()
        folds.append(dict(fold=fi+1, n=len(test), trainN=len(train),
                          trainBlocks=sorted(set(groups[train])), testBlocks=sorted(set(groups[test])),
                          rmse=float(np.sqrt(errors.mean())), baselineRmse=float(np.sqrt(np.mean((y[test]-baseline[test])**2)))))
        fold_weights.append(len(test) / n)
    notify('正在汇总因子排序与响应规律…')
    repeated = np.einsum('f,fjr->jr', fold_weights, deltas)
    means = repeated.mean(axis=1)
    fold_means = deltas.mean(axis=2)
    positive = np.maximum(means, 0)
    mse = float(np.mean((y-predictions)**2))
    base_mse = float(np.mean((y-baseline)**2))
    r2 = 1 - np.sum((y-predictions)**2) / np.sum((y-y.mean())**2)
    skill = 1-mse/base_mse if base_mse > 0 else None
    reliable = skill is not None and skill > 0 and (binary or r2 > 0)
    top = np.argmax(fold_means, axis=1)
    ranking = [dict(key=k, delta=float(means[j]), sd=float(repeated[j].std(ddof=1)),
                    share=float(positive[j]/positive.sum()*100) if reliable and positive.sum() > 0 else None,
                    positiveFolds=int(np.sum(fold_means[:, j] > 0)),
                    firstFolds=int(sum(top[f] == j and fold_means[f, j] > 0 for f in range(nf))))
               for j, k in enumerate(keys)]
    ranking.sort(key=lambda item: -item['delta'])
    correlations = []
    for ai, j in enumerate(numeric_idx):
        for l in numeric_idx[ai+1:]:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                rho = float(spearmanr(x[:, j].astype(float), x[:, l].astype(float)).statistic)
            if np.isfinite(rho) and abs(rho) >= .7:
                correlations.append(dict(a=keys[j], b=keys[l], rho=rho))
    full = create_model()
    full.fit(x, y)
    dependence = []
    for j, k in enumerate(keys):
        categorical_feature = k in categorical
        if categorical_feature:
            grid = sorted(set(x[:, j]))
        else:
            values = x[:, j].astype(float)
            grid = np.unique(values) if len(np.unique(values)) <= 10 else np.linspace(*np.quantile(values, [.05, .95]), 25)
        curves = np.tile(x, (len(grid), 1))
        for gi, value in enumerate(grid):
            curves[gi*n:(gi+1)*n, j] = value
        partial = predict(full, curves).reshape(len(grid), n).mean(axis=1)
        points = [dict(x=value, y=float(mean)) for value, mean in zip(grid, partial)]
        dependence.append(dict(key=k, categorical=categorical_feature, points=points,
                               observed=[dict(plot=r['plot'], x=r[k], y=r[target]) for r in complete]))
    notes = [
        f'{n} 个完整样方来自 {nblocks} 个大样地；{nf} 折按大样地留出验证。每个样方仅在未参与训练时预测一次；同一大样地不跨训练与验证。',
        f'在各验证折内逐列打乱 {REPEATS} 次，按验证样本数加权汇总 ΔMSE（分类为 ΔBrier）。文本分类整体置换，独热编码只在训练折学习。负值原样保留，不作显著性检验。',
        '相对预测重要性 = 正的平均误差增量 / 所有正增量之和 × 100%；它不是解释率、独立生态贡献或因果效应。负增量在百分比分母中记为 0。模型未优于基准或回归 R²≤0 时不报告百分比。',
        '均值基准仅使用各训练折的响应均值。交叉验证 R²由全部留出预测合并计算；误差单位与当前响应相同。每折正增量次数反映排序对留出大样地的敏感性，置换 SD 不是置信区间。',
        '偏依赖曲线用全部完整样本重新拟合，并对其他因子的观测分布取平均；它用于描述模型，不是独立验证、因果效应或最适环境阈值。连续横轴为观测 5%–95% 分位区间（少数取值时显示全部取值）。',
        '强相关因子可能互相替代、分摊重要性；打乱或绘制偏依赖也可能产生少见的环境组合，应结合散点、相关和生态机制解释。',
        '当前未使用样地编号作预测因子；留出验证检验对新大样地的预测，不能分离地内与地间效应，也不能消除未测量混杂。',
        '参数固定，不依据当前验证结果自动调参或筛变量。反复比较模型后选择最好者仍可能乐观，正式研究宜预先确定模型或另设独立验证样地。',
        '仅有少量独立大样地，所有排序与规律均为探索性。计数、均值形态与出现状态分别建模；无该级植株时的形态均值不补 0。',
    ]
    if dropped:
        notes.append('已排除无变异变量：' + '、'.join(eligible[k]['label'] for k in dropped))
    if not reliable:
        notes.append('当前模型未满足超越基准且具备正预测表现的条件，不能据此认定某个环境因子最重要。')
    if target != 'density':
        notes.append('当前响应未按面积标准化；若样方面积不同，请先填写面积，再选择更新密度。树模型没有使用计数回归的面积 offset。')
    result = dict(method=method, name=METHODS[method]+('分类' if binary else '回归'), binary=binary,
                  target=target, n=n, excluded=len(rows)-n, blocks=nblocks, predictors=keys,
                  dropped=dropped, folds=folds, repeats=REPEATS, seed=SEED, reliable=reliable,
                  parameters=params if method != 'boost' else dict(n_estimators=120, learning_rate=.03, max_depth=2, min_samples_leaf=4, random_state=SEED),
                  metrics=dict(r2=None if binary else float(r2), rmse=math.sqrt(mse), mae=float(np.mean(abs(y-predictions))),
                               baselineRmse=math.sqrt(base_mse), skill=skill,
                               auc=float(roc_auc_score(y, predictions)) if binary else None, brier=mse if binary else None),
                  importance=ranking, dependence=dependence, correlated=correlations, notes=notes,
                  predictions=[dict(plot=r['plot'], block=r['block'], observed=float(y[i]), predicted=float(predictions[i]), baseline=float(baseline[i])) for i, r in enumerate(complete)])
    return clean(result)
