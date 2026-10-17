"""Public-service isolation, import, recalculation and request-boundary checks."""
import base64
import copy
import io
import unittest

import openpyxl
from web import app, MAX_ROWS


class PublicServiceTest(unittest.TestCase):
    def setUp(self):
        self.visitor = app.test_client()
        self.other = app.test_client()
        self.example = self.visitor.get('/api/data').get_json()

    def test_public_example_has_no_local_path(self):
        self.assertEqual(self.example['mode'], 'example')
        self.assertEqual(self.example['sourcePath'], '')
        self.assertNotIn('/Users/', str(self.example))
        self.assertEqual(len(self.example['dataset']['rows']), 48)

    def test_visitor_edits_recalculate_without_changing_example(self):
        data = copy.deepcopy(self.example['dataset'])
        data['rows'][0]['n1'] = 100
        data['columns'].append(dict(key='soil', label='土壤含水率', role='environment', unit='%'))
        for i, row in enumerate(data['rows']):
            row['soil'] = i / 2
        response = self.visitor.post('/api/analyze', json=dict(dataset=data))
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result['overview']['total'], sum(float(r['n1'])+float(r['n2'])+float(r['n3']) for r in data['rows']))
        self.assertEqual(result['overview']['envCount'], sum(c['role'] in ('environment', 'categorical') for c in data['columns']))
        self.assertIn('0<H≤20', result['heightDefinition'])
        self.assertEqual(self.other.get('/api/data').get_json()['dataset'], self.example['dataset'])
        self.assertEqual(self.visitor.post('/api/draft', json=dict(dataset=data)).status_code, 405)

    def test_xlsx_and_csv_imports_are_isolated_and_join_by_id(self):
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(['样方编号', 'I 级株数', '样方编号', '郁闭度'])
        sheet.append(['1-1', 2, '1-2', 80])
        sheet.append(['1-2', 3, '1-1', 50])
        content = io.BytesIO()
        book.save(content)
        response = self.visitor.post('/api/import', json=dict(name='观测.xlsx', base64=base64.b64encode(content.getvalue()).decode()))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['dataset']['rows'][0]['canopy'], 50)
        csv_data = '样方编号,郁闭度,I 级株数,新变量\n2-1,60,5,42\n'
        response = self.visitor.post('/api/import', json=dict(name='样方.csv', base64=base64.b64encode(csv_data.encode()).decode()))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(c['label'] == '新变量' for c in response.get_json()['dataset']['columns']))
        self.assertEqual(self.other.get('/api/data').get_json()['dataset'], self.example['dataset'])

    def test_invalid_input_and_old_write_routes_are_rejected(self):
        data = copy.deepcopy(self.example['dataset'])
        data['rows'] *= (MAX_ROWS // len(data['rows'])) + 1
        self.assertEqual(self.visitor.post('/api/analyze', json=dict(dataset=data)).status_code, 400)
        self.assertEqual(self.visitor.post('/api/import', json=dict(name='evil.exe', base64='AA==')).status_code, 400)
        self.assertEqual(self.visitor.post('/api/import', json=dict(name='bad.xlsx', base64='AA==')).status_code, 400)
        self.assertEqual(self.visitor.post('/api/config', json={}).status_code, 405)
        self.assertEqual(self.visitor.get('/.env').status_code, 404)
        self.assertEqual(self.visitor.get('/api/data').headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
