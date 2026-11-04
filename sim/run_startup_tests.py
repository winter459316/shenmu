from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
runtime=ROOT/'.runtime/zu4ev_stereo/launcher'
if not runtime.is_dir():raise SystemExit('Assemble the 2026.1 runtime first; see README.md.')
sys.path.insert(0,str(runtime))
suite=unittest.defaultTestLoader.discover(str(ROOT/'sim/startup'),pattern='test_*.py')
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
