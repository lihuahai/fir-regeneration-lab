"""Scientific acceptance tests for grouped prediction and feature interpretation."""
import copy
import unittest
import numpy as np
from engine import parse_table, prepared
from importance import fit_importance, group_splits


class ImportanceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(57)
        matrix = [['样方编号', '郁闭度', 'I 级株数', 'II 级株数', 'III 级株数', '土壤信号', '无关噪声', '坡向']]
        for block in range(12):
            for j in range(6):
                x = float(rng.uniform(-2, 2))
                y = int(round(10+40*x*x))
                matrix.append([f'{block+1}--{j+1}', float(rng.uniform(10, 90)), y, 0, 0,
                               x, float(rng.normal()), ['阴坡', '阳坡'][j % 2]])
        cls.data = parse_table(matrix)
        cls.keys = {c['label']: c['key'] for c in cls.data['columns']}

    def test_whole_big_plots_are_held_out_once(self):
        groups = np.repeat(np.arange(12), 6)
        counts = np.zeros(len(groups), dtype=int)
        for train, test in group_splits(groups):
            self.assertFalse(set(groups[train]) & set(groups[test]))
            counts[test] += 1
        self.assertTrue(np.all(counts == 1))

    def test_nonlinear_signal_beats_noise_without_mutating_input(self):
        snapshot = copy.deepcopy(self.data)
        result = fit_importance(self.data)
        self.assertEqual(self.data, snapshot)
        self.assertTrue(result['reliable'])
        self.assertGreater(result['metrics']['r2'], .6)
        self.assertEqual(result['importance'][0]['key'], self.keys['土壤信号'])
        self.assertGreater(result['importance'][0]['share'], 70)
        self.assertAlmostEqual(sum(r['share'] for r in result['importance']), 100)
        self.assertTrue(next(c for c in result['dependence'] if c['key']==self.keys['坡向'])['categorical'])
        for fold in result['folds']:
            self.assertFalse(set(fold['trainBlocks']) & set(fold['testBlocks']))

    def test_non_predictive_model_does_not_claim_percent_contribution(self):
        data = copy.deepcopy(self.data)
        # Signals reverse by big plot; a constant category-only predictor cannot beat a mean baseline.
        for b in range(12):
            for j in range(6):
                data['rows'][b*6+j]['n1'] = 0 if b%2 else 100
        result = fit_importance(data, {'mlPredictors':[self.keys['坡向']]})
        self.assertFalse(result['reliable'])
        self.assertTrue(all(r['share'] is None for r in result['importance']))

    def test_classification_and_missing_morphology(self):
        data = copy.deepcopy(self.data)
        for i, row in enumerate(data['rows']):
            row['n1'] = 1 if float(row[self.keys['土壤信号']])>0 else 0
        result = fit_importance(data, {'target':'presence', 'mlMethod':'extra'})
        self.assertTrue(result['binary'])
        self.assertIsNone(result['metrics']['r2'])
        self.assertGreater(result['metrics']['auc'], .9)
        self.assertTrue(all(0<=p['predicted']<=1 for p in result['predictions']))
        rows, cols, _ = prepared(self.data, {})
        self.assertEqual(next(c for c in cols if c['label']=='坡向')['role'], 'categorical')
        self.assertIn(rows[0][self.keys['坡向']], ('阴坡', '阳坡'))
        with self.assertRaisesRegex(ValueError, '环境因子'):
            fit_importance(data, {'mlPredictors':['n1']})


if __name__ == '__main__':
    unittest.main()
