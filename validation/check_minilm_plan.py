"""Offline metadata-parser checks; no ML imports, network or installations."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.plan_minilm_runtime import freeze_map, select_cpu_wheel, WHEEL


class PlanTests(unittest.TestCase):
    def link(self, host='download.pytorch.org', wheel=WHEEL, fragment='sha256='+'a'*64):
        return '<a href="https://{}/whl/cpu/{}#{}">wheel</a>'.format(host, wheel.replace('+', '%2B'), fragment)

    def test_official_cpu_wheel(self):
        self.assertIn('%2Bcpu', select_cpu_wheel(self.link()))
        self.assertIn('download-r2', select_cpu_wheel(self.link(host='download-r2.pytorch.org')))

    def test_wrong_cpu_arch_or_version_rejected(self):
        for wheel in (WHEEL.replace('aarch64', 'x86_64'), WHEEL.replace('cp312', 'cp311'), WHEEL.replace('+cpu', ''), WHEEL.replace('2.9.1', '2.9.0')):
            with self.subTest(wheel=wheel), self.assertRaises(ValueError):
                select_cpu_wheel(self.link(wheel=wheel))

    def test_wrong_host_or_missing_hash_rejected(self):
        for html in (self.link(host='example.com'), self.link(fragment=''), self.link(fragment='sha256=bad')):
            with self.assertRaises(ValueError):
                select_cpu_wheel(html)

    def test_two_distinct_urls_rejected(self):
        with self.assertRaises(ValueError):
            select_cpu_wheel(self.link()+self.link(host='download-r2.pytorch.org'))

    def test_exact_baseline_and_normalized_names(self):
        self.assertEqual(freeze_map('# header\nChroma_hnswlib==0.7.3\nnumpy==1.26.4\n'),
                         {'chroma-hnswlib': '0.7.3', 'numpy': '1.26.4'})
        for text in ('', 'numpy>=1.26', '-e .', 'numpy==1\nNumPy==2'):
            with self.assertRaises(ValueError):
                freeze_map(text)

    def test_no_ml_imports_and_python38_syntax(self):
        ast.parse((ROOT/'validation/plan_minilm_runtime.py').read_text(encoding='utf-8'), feature_version=(3, 8))
        self.assertFalse(any(name in sys.modules for name in ('torch', 'transformers', 'chromadb', 'openai')))


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
