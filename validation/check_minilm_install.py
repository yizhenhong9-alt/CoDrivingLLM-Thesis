"""Offline installation guards only, no ML imports or package mutations."""
from pathlib import Path
import sys
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.verify_minilm_install import ADDITIONS, CPU_URL, approved_requirements, verify_versions


class InstallTests(unittest.TestCase):
    def test_before_and_after(self):
        baseline = {'chromadb': '0.4.15', 'numpy': '1.26.4'}
        verify_versions(baseline, dict(baseline), False)
        verify_versions(baseline, dict(baseline, **ADDITIONS), True)

    def test_baseline_change_rejected(self):
        baseline = {'numpy': '1.26.4'}
        for current in ({'numpy': '2.0.0'}, dict(baseline, surprise='1.0')):
            with self.assertRaises(ValueError):
                verify_versions(baseline, current, False)

    def test_unapproved_version_or_missing_package_rejected(self):
        baseline = {'chromadb': '0.4.15'}
        current = dict(baseline, **ADDITIONS)
        current['torch'] = '2.9.1'
        with self.assertRaises(ValueError):
            verify_versions(baseline, current, True)
        current.pop('torch')
        with self.assertRaises(ValueError):
            verify_versions(baseline, current, True)

    def test_partial_install_is_not_accepted_as_pristine(self):
        with self.assertRaises(ValueError):
            verify_versions({'chromadb': '0.4.15'}, {'chromadb': '0.4.15', 'torch': ADDITIONS['torch']}, False)

    def test_cpu_url_hash_and_exact_pins(self):
        lines = approved_requirements().splitlines()
        self.assertEqual(len(lines), 9)
        self.assertEqual(lines[0], 'torch @ '+CPU_URL)
        self.assertEqual(len(urlsplit(CPU_URL).fragment.split('=')[1]), 64)
        self.assertFalse(any(name in sys.modules for name in ('torch', 'transformers', 'chromadb')))


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
