"""Offline source verification tests; no network, torch, or model loading."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation.accept_minilm_embedding import (FILES, REVISION, select_files,
                                               verify_file, convert_verified_weights)


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
        info['siblings'] = [v for v in info['siblings'] if v['rfilename'] != 'pytorch_model.bin']
        with self.assertRaisesRegex(ValueError, 'pytorch_model.bin'):
            select_files(info)

    def test_pinned_old_format_without_safetensors(self):
        selected = select_files(self.info())
        self.assertIn('pytorch_model.bin', selected)
        self.assertNotIn('model.safetensors', selected)

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


class ConversionTests(unittest.TestCase):
    def conversion(self, invalid=False, corrupt=False, existing=False):
        class Tensor:
            def detach(self): return self
            def cpu(self): return self
            def contiguous(self): return self
            def clone(self): return self
        with tempfile.TemporaryDirectory() as folder:
            snapshot = Path(folder)/'snapshot'
            run = Path(folder)/'run'
            snapshot.mkdir()
            run.mkdir()
            source = snapshot/'pytorch_model.bin'
            source.write_bytes(b'bad' if corrupt else b'abc')
            expected = dict(size=3, algorithm='sha256', digest=hashlib.sha256(b'abc').hexdigest())
            if existing:
                (snapshot/'model.safetensors').write_bytes(b'existing')
            loader = Mock(return_value={'weight': object() if invalid else Tensor()})
            def save(tensors, filename, metadata):
                self.assertEqual(metadata, {'format': 'pt'})
                self.assertIsInstance(tensors['weight'], Tensor)
                Path(filename).write_bytes(b'converted')
            modules = {'torch': SimpleNamespace(Tensor=Tensor, load=loader, __version__='test'),
                       'safetensors': SimpleNamespace(),
                       'safetensors.torch': SimpleNamespace(save_file=save)}
            with patch.dict(sys.modules, modules):
                if invalid or corrupt or existing:
                    with self.assertRaises(ValueError):
                        convert_verified_weights(snapshot, run, expected)
                    if corrupt:
                        loader.assert_not_called()
                    if existing:
                        self.assertEqual((snapshot/'model.safetensors').read_bytes(), b'existing')
                else:
                    record = convert_verified_weights(snapshot, run, expected)
                    loader.assert_called_once_with(str(source), map_location='cpu', weights_only=True)
                    self.assertTrue(record['weights_only'])
                    self.assertEqual((snapshot/'model.safetensors').read_bytes(), b'converted')

    def test_restricted_conversion(self): self.conversion()
    def test_reject_non_tensor(self): self.conversion(invalid=True)
    def test_verify_before_load(self): self.conversion(corrupt=True)
    def test_preserve_existing_derived_file(self): self.conversion(existing=True)


if __name__ == '__main__':
    unittest.main()
