"""Regression tests for result identities, schemas, and saved ROOT values."""

import contextlib
import csv
import io
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import uproot

REPO = Path(__file__).resolve().parents[1]
for folder in ('CQC', 'SQC', 'scirpt'):
    sys.path.insert(0, str(REPO / folder))

import yield_tables
from collect_sensor_yields import collect
from compare_sensor_yields import compare
from summarize_sensor_yields import summarize
from collect_results import collect_summary, METRICS
from extract_sensor_vbd_results import extract_result_root
from make_condor_jobs import generate_collector
from plot_sqc_cqc_vbd_residuals import read_cqc_channels, read_sqc_pad_values


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def write_tree(path, name, arrays):
    path.parent.mkdir(parents=True, exist_ok=True)
    with uproot.recreate(path) as stream:
        stream.mktree(name, {key: values.dtype for key, values in arrays.items()})
        stream[name].extend(arrays)


class PostProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wafer(self, parent, name, statuses=('A', 'B1', 'C')):
        path = parent / name
        write_csv(path / 'sensorYield.csv', ['Sensor', 'Final_Status'],
                  [{'Sensor': i, 'Final_Status': status} for i, status in enumerate(statuses, 1)])
        return path

    def sample(self, parent, name):
        (parent / name / '20WS0012300001').mkdir(parents=True)

    def test_cern_relative_paths(self):
        self.assertEqual(yield_tables.resolve_path('CQC_results/CERN/batch'),
                         Path('/eos/user/l/liaoc/public/HGTD_sensor/CQC_results/CERN/batch'))
        self.assertEqual(yield_tables.resolve_path(self.root), self.root)

    def test_collect_normalizes_identity_and_groups_only_known_b_statuses(self):
        self.wafer(self.root / 'results', 'B23_1', ('A', 'B', 'B1', 'B2', 'C'))
        self.sample(self.root / 'sample', 'B23-01')
        target, counts = collect(self.root / 'results', self.root / 'sample', self.root / 'out')
        self.assertEqual(counts, {'A': 1, 'B': 3, 'C': 1})
        self.assertEqual({row['wafer_name'] for row in read_csv(target / 'B.csv')}, {'B23_1'})

    def test_unknown_status_rejected_before_write(self):
        self.wafer(self.root / 'results', 'B23_1', ('Unknown',))
        self.sample(self.root / 'sample', 'B23_1')
        with self.assertRaisesRegex(ValueError, 'unknown Final_Status'):
            collect(self.root / 'results', self.root / 'sample', self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_status_only_vendor_table_preserves_other_wafers_metrics(self):
        first = self.wafer(self.root / 'results', 'B23_1', ('A',))
        write_csv(first / 'sensorYield.csv', ['Sensor', 'Vbd_Average', 'Final_Status'],
                  [{'Sensor': 1, 'Vbd_Average': '180.123', 'Final_Status': 'A'}])
        self.wafer(self.root / 'results', 'B23_2', ('A',))
        self.sample(self.root / 'sample', 'B23_1')
        self.sample(self.root / 'sample', 'B23_2')
        output, _ = collect(self.root / 'results', self.root / 'sample', self.root / 'out')
        rows = read_csv(output / 'A.csv')
        self.assertEqual([row['Vbd_Average'] for row in rows], ['180.123', ''])

    def test_ambiguous_yield_and_serial_rejected(self):
        path = self.wafer(self.root, 'B23_1')
        (path / 'sensorYields.csv').write_text((path / 'sensorYield.csv').read_text())
        with self.assertRaisesRegex(ValueError, 'expected one sensor yield table'):
            yield_tables.find_yield_file(path)
        (path / '20WS0012300001').mkdir()
        (path / '20WS0012300002').mkdir()
        with self.assertRaisesRegex(ValueError, 'expected one 20WS serial'):
            yield_tables.wafer_serial(path)

    def test_serial_prefers_zip_name_over_extracted_directory(self):
        path = self.root / 'sample' / 'B23_1'
        path.mkdir(parents=True)
        (path / '20WS0012300007.zip').write_bytes(b'')
        self.assertEqual(yield_tables.wafer_serial(path), '20WS0012300007')
        (path / '20WS0012300001').mkdir()
        self.assertEqual(yield_tables.wafer_serial(path), '20WS0012300007')
        (path / 'unrelated.zip').write_bytes(b'')
        self.assertEqual(yield_tables.wafer_serial(path), '20WS0012300007')
        (path / '20WS0012300008.zip').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'expected at most one serial ZIP'):
            yield_tables.wafer_serial(path)

    def test_serial_zip_must_agree_with_extracted_directories(self):
        path = self.root / 'sample' / 'B23_1'
        path.mkdir(parents=True)
        (path / '20WS0012300007.zip').write_bytes(b'')
        (path / '20WS0012300009').mkdir()
        with self.assertRaisesRegex(ValueError, 'disagrees with extracted'):
            yield_tables.wafer_serial(path)
        (path / '20WS0012300007').mkdir()
        with self.assertRaisesRegex(ValueError, 'disagrees with extracted'):
            yield_tables.wafer_serial(path)

    def test_duplicate_sensor_rejected(self):
        path = self.root / 'sensorYield.csv'
        write_csv(path, ['Sensor', 'Final_Status'],
                  [{'Sensor': 1, 'Final_Status': 'A'}, {'Sensor': 1, 'Final_Status': 'B1'}])
        with self.assertRaisesRegex(ValueError, 'duplicate sensor'):
            yield_tables.read_yields(path)

    def test_compare_requires_equal_identity_sets(self):
        self.wafer(self.root / 'ihep', 'B23_1')
        self.wafer(self.root / 'ime', 'B23-01', ('A', 'B1'))
        self.sample(self.root / 'sample', 'B23_1')
        with self.assertRaisesRegex(ValueError, 'sensor sets differ'):
            compare(self.root / 'ihep', self.root / 'ime', self.root / 'sample')
        self.wafer(self.root / 'ime', 'B23-01', ('B1', 'B1', 'C'))
        output, count = compare(self.root / 'ihep', self.root / 'ime', self.root / 'sample')
        self.assertEqual(count, 1)
        self.assertEqual([r['Test'] for r in read_csv(output)], ['IHEP', 'IME'])
        self.wafer(self.root / 'ime', 'B23_2')
        with self.assertRaisesRegex(ValueError, 'wafer sets differ'):
            compare(self.root / 'ihep', self.root / 'ime', self.root / 'sample')

    def test_summary_rejects_missing_identity(self):
        self.wafer(self.root / 'ihep', 'B23_1')
        self.wafer(self.root / 'ime', 'B23_1', ('A', 'B1'))
        self.sample(self.root / 'sample', 'B23_1')
        collect(self.root / 'ihep', self.root / 'sample', self.root / 'out')
        collect(self.root / 'ime', self.root / 'sample', self.root / 'out', 'IME')
        with self.assertRaisesRegex(ValueError, 'sets differ'):
            summarize(self.root / 'out')

    def test_root_export_preserves_cqc_precision_and_sentinels(self):
        directory = self.wafer(self.root, 'B23_1', ('A',))
        path = directory / 'B23_1.root'
        arrays = {'sensor_id': np.array([1, 1], dtype='i4'),
                  'channel_id': np.array([1, 2], dtype='i4'),
                  'vbd_corrected_20C_V': np.array([180.123456789, -2.2]),
                  'leakage_current_A': np.array([2.34567891e-7, 0.0])}
        write_tree(path, 'ChannelResults', arrays)
        with contextlib.redirect_stdout(io.StringIO()):
            outputs = extract_result_root(path, 'CQC', self.root / 'export')
        rows = read_csv(outputs[0])
        self.assertEqual([float(r['vbd_20C_V']) for r in rows], arrays['vbd_corrected_20C_V'].tolist())
        self.assertEqual(float(rows[0]['leakage_current_A']), arrays['leakage_current_A'][0])

    def test_sqc_export_requires_both_trees_before_writing(self):
        path = self.root / 'B23' / 'W01-P1' / 'W01-P1.root'
        write_tree(path, 'SQC_results', {'pad_position': np.arange(1, 226, dtype='i4'),
                  'vbd_corrected_20C_V': np.full(225, 180.123456789),
                  'leakage_current_A': np.full(225, 2e-8)})
        with self.assertRaisesRegex(ValueError, 'missing TTree CQC_results'):
            extract_result_root(path, 'SQC', self.root / 'export')
        self.assertFalse((self.root / 'export').exists())
        with uproot.update(path) as stream:
            arrays = {'channel_id': np.arange(1, 16, dtype='i4'),
                      'vbd_corrected_20C_V': np.full(15, 175.987654321),
                      'leakage_current_A': np.full(15, 3e-7)}
            stream.mktree('CQC_results', {k: a.dtype for k, a in arrays.items()})
            stream['CQC_results'].extend(arrays)
        with contextlib.redirect_stdout(io.StringIO()):
            outputs = extract_result_root(path, 'SQC', self.root / 'export')
        self.assertEqual([len(read_csv(p)) for p in outputs], [225, 15])
        self.assertEqual(float(read_csv(outputs[0])[0]['vbd_corrected_20C_V']), 180.123456789)

    def test_duplicate_channel_rejected_before_vbd_filter(self):
        path = self.root / 'duplicate.root'
        write_tree(path, 'CQC_results', {'channel_id': np.array([1, 1], dtype='i4'),
                  'vbd_corrected_20C_V': np.array([999.0, 180.0])})
        with self.assertRaisesRegex(ValueError, 'duplicate channel_id'):
            read_cqc_channels(path)

    def test_fractional_pad_id_not_truncated(self):
        path = self.root / 'fractional.root'
        write_tree(path, 'SQC_results', {'pad_position': np.array([1.5]),
                  'vbd_corrected_20C_V': np.array([180.0])})
        with self.assertRaisesRegex(ValueError, 'finite integers'):
            read_sqc_pad_values(path)

    def sqc_batch(self, name, missing=False):
        directory = self.root / name
        fields = ['output_group', 'output_sensor', 'label', 'Tp', 'Tn', 'cqc']
        plan = [{'output_group': 'B23', 'output_sensor': 'W01-P1', 'label': 'sensor',
                 'Tp': '21.5', 'Tn': '20.0', 'cqc': 'matched:B23_1'}]
        if missing:
            plan.append({**plan[0], 'output_sensor': 'W01-P2'})
        write_csv(directory / 'sensor_plan.csv', fields, plan)
        rows = [{'Group': group, **dict(zip(METRICS, ['180', '2', '175', '1.11%', '1.5', '1e-8', '2e-8', valid]))}
                for group, valid in [('ProbeCard', '15'), ('Needle', '225')]]
        write_csv(directory / 'B23/W01-P1/crosscheck.csv', ['Group', *METRICS], rows)
        return directory

    def test_sqc_multibatch_identity_temperature_and_missing(self):
        self.sqc_batch('1nd_batch', missing=True)
        self.sqc_batch('2nd_batch')
        with contextlib.redirect_stdout(io.StringIO()):
            output, sensors, missing = collect_summary(self.root)
        rows = read_csv(output)
        self.assertEqual(sensors, 2)
        self.assertEqual(len(rows), 4)
        self.assertEqual({r['batch'] for r in rows}, {'1nd_batch', '2nd_batch'})
        self.assertEqual({r['Tn'] for r in rows}, {'20.0'})
        self.assertEqual(missing, ['1nd_batch/B23/W01-P2'])

    def test_generated_collector_uses_configured_root(self):
        jobs = self.root / 'jobs'
        jobs.mkdir()
        generate_collector(jobs, Path('/eos/user/l/liaoc/public/HGTD_sensor/SQC_results/CERN/2nd_batch'))
        script = (jobs / 'collect_results.py').read_text()
        self.assertIn("DEFAULT_ROOT = '/eos/user/l/liaoc/public/HGTD_sensor/SQC_results/CERN/2nd_batch'", script)
        compile(script, str(jobs / 'collect_results.py'), 'exec')


if __name__ == '__main__':
    unittest.main()
