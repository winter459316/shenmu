"""Archive safety and tamper tests using tiny synthetic assets, never the board."""
from pathlib import Path
import hashlib,importlib.util,json,tempfile,unittest,zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_runtime',ROOT/'board/deploy/prepare_runtime.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class PrepareTests(unittest.TestCase):
    def fixture(self,folder):
        root=Path(folder);(root/'board/config').mkdir(parents=True)
        data=b'reference';digest=hashlib.sha256(data).hexdigest()
        (root/'board/config/source_map.json').write_text('[]')
        (root/'board/config/runtime_assets.json').write_text(json.dumps({'files':{'data.bin':{'sha256':digest,'bytes':len(data)}}}))
        return root,data

    def test_reject_paths(self):
        for name in ('../outside','/absolute','C:/drive','a\\b','a/../b'):
            with self.assertRaises(ValueError):module.safe(name)

    def test_reject_tamper_and_extra_entries(self):
        for extra in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                root,data=self.fixture(folder);archive=root/'assets.zip'
                with zipfile.ZipFile(archive,'w') as z:
                    z.writestr('data.bin',data if extra else b'corrupted')
                    if extra:z.writestr('extra',b'x')
                with self.assertRaises(ValueError):module.prepare(archive,root)
                self.assertFalse((root/'.runtime/zu4ev_stereo').exists())

    def test_reuse_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root,data=self.fixture(folder);archive=root/'assets.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('data.bin',data)
            result=module.prepare(archive,root)
            self.assertTrue((result/'candidates/usb_fast_infer2/captures').is_dir())
            self.assertTrue((result/'candidates/usb_fast_infer2/recordings').is_dir())
            self.assertEqual(result,module.prepare(archive,root))
            (result/'data.bin').write_bytes(b'changed')
            with self.assertRaises(ValueError):module.prepare(archive,root)
            self.assertEqual((result/'data.bin').read_bytes(),b'changed')

if __name__=='__main__':unittest.main(verbosity=2)
