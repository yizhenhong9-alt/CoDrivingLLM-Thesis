"""Offline source verification tests; no network, torch, or model loading."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation.accept_minilm_embedding import FILES, REVISION, select_files, verify_file


class SourceTests(unittest.TestCase):
    def info(self):
        return dict(sha=REVISION, siblings=[dict(rfilename=name, size=3, blobId='a'*40)
                                           for name in FILES])

    def test_revision(self):
        info = self.info()
        info['sha'] = 'main'
        with self.assertRaises(ValueError):
            select_files(info)

    def test_missing_weights(self):
        info = self.info()
        info['siblings'] = [v for v in info['siblings'] if v['rfilename'] != 'model.safetensors']
        with self.assertRaises(KeyError):
            select_files(info)

    def test_allowlist(self):
        info = self.info()
        info['siblings'].append(dict(rfilename='../escape'))
        self.assertEqual(set(select_files(info)), set(FILES))

    def test_lfs(self):
        info = self.info()
        info['siblings'][0]['lfs'] = dict(size=3, sha256='b'*64)
        self.assertEqual(select_files(info)[FILES[0]]['algorithm'], 'sha256')

    def test_invalid_size(self):
        info = self.info()
        info['siblings'][0]['size'] = -1
        with self.assertRaises(ValueError):
            select_files(info)

    def test_hashes_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'file'
            path.write_bytes(b'abc')
            for algorithm, digest in [('sha256', hashlib.sha256(b'abc').hexdigest()),
                                      ('git-sha1', hashlib.sha1(b'blob 3\0abc').hexdigest())]:
                expected = dict(size=3, algorithm=algorithm, digest=digest)
                self.assertEqual(verify_file(path, expected), hashlib.sha256(b'abc').hexdigest())
                path.write_bytes(b'abd')
                with self.assertRaises(ValueError):
                    verify_file(path, expected)
                path.write_bytes(b'abc')


if __name__ == '__main__':
    unittest.main()
