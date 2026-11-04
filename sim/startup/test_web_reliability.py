"""Loopback/mocked tests only; never connect to board or serial."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import importlib,io,json,sys,tempfile,unittest
from contextlib import redirect_stdout
P=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(P/'.runtime/zu4ev_stereo/launcher'))
import legacy_adapter
sys.path.insert(0,str(P/'board/deploy/launcher'))
import startup,viewer_identity as v

class Tests(unittest.TestCase):
 def state(self):return {k:{'reachable':False,'status':{}} for k in startup.ENDPOINTS}
 def test_open_never_probes_or_repairs_board(self):
  with patch('sys.argv',['startup','open']),patch.object(startup,'check_local'),patch.object(startup,'ensure_viewer') as ensure,patch.object(startup,'snapshot') as probe,patch.object(startup,'run') as run,redirect_stdout(io.StringIO()):startup.main()
  ensure.assert_called_once();probe.assert_not_called();run.assert_not_called()
 def test_start_local_before_offline_board_probe(self):
  order=[];state=self.state()
  with patch('sys.argv',['startup','start']),patch.object(startup,'check_local'),patch.object(startup,'ensure_viewer',side_effect=lambda *_:order.append('pc')),patch.object(startup,'snapshot',side_effect=lambda:order.append('probe') or state),patch.object(startup,'run') as run,redirect_stdout(io.StringIO()):startup.main()
  self.assertEqual(order[:2],['pc','probe']);run.assert_not_called()
 def test_board_setup_failure_does_not_close_viewer(self):
  state=self.state();state['model']=dict(reachable=True,status=dict(ready=True,version='fast_pl3_usable_v5_quad'),worker_state='ready');state['section']=dict(reachable=True,status=dict(active=False,switching=False))
  with patch('sys.argv',['startup','start']),patch.object(startup,'check_local'),patch.object(startup,'ensure_viewer') as ensure,patch.object(startup,'snapshot',return_value=state),patch.object(startup,'run',side_effect=RuntimeError('fixture service error')),redirect_stdout(io.StringIO()) as output:startup.main()
  self.assertIn('板端准备未完成',output.getvalue());self.assertTrue(ensure.called)
 def test_unknown_section_blocks_automatic_repair(self):
  state=self.state();state['model']=dict(reachable=True,status=dict(ready=True,version='fast_pl3_usable_v5_quad'),worker_state='ready')
  with patch('sys.argv',['startup','start']),patch.object(startup,'check_local'),patch.object(startup,'ensure_viewer'),patch.object(startup,'snapshot',return_value=state),patch.object(startup,'run') as run,redirect_stdout(io.StringIO()):startup.main()
  run.assert_not_called()
 def test_matching_service_reused_without_child(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',return_value=v.identity(Path(d))),patch.object(v.subprocess,'Popen') as spawn:self.assertFalse(v.ensure_viewer(d)['started']);spawn.assert_not_called()
 def test_other_package_is_not_silently_reused(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',return_value=v.identity(Path(d)/'other')),patch.object(v.subprocess,'Popen') as spawn:
   with self.assertRaisesRegex(RuntimeError,'8849'):v.ensure_viewer(d)
   spawn.assert_not_called()
 def test_unresponsive_listener_is_not_killed_or_overwritten(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',side_effect=OSError()),patch.object(v,'listening',return_value=True),patch.object(v.subprocess,'Popen') as spawn:
   with self.assertRaisesRegex(RuntimeError,'8849'):v.ensure_viewer(d)
   spawn.assert_not_called()
 def test_new_child_must_return_matching_identity(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',side_effect=[OSError(),v.identity(Path(d))]),patch.object(v,'listening',return_value=False),patch.object(v.subprocess,'Popen',return_value=SimpleNamespace(pid=123,poll=lambda:None)):
   result=v.ensure_viewer(d);self.assertTrue(result['started']);self.assertEqual(result['pid'],123)
 def test_exited_child_fails_without_board_recovery(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',side_effect=OSError()),patch.object(v,'listening',return_value=False),patch.object(v.subprocess,'Popen',return_value=SimpleNamespace(poll=lambda:1)):
   with self.assertRaisesRegex(RuntimeError,'进程启动失败'):v.ensure_viewer(d)
 def test_new_child_timeout_is_reported(self):
  with tempfile.TemporaryDirectory() as d,patch.object(v,'get_identity',side_effect=OSError()),patch.object(v,'listening',return_value=False),patch.object(v.subprocess,'Popen',return_value=SimpleNamespace(poll=lambda:None)),patch.object(v.time,'sleep'):
   with self.assertRaisesRegex(RuntimeError,'超时'):v.ensure_viewer(d,timeout=.001)
 def test_old_toolchain_rejected_even_if_other_checks_pass(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);paths=['candidates/usb_fast_infer2/hardware_verified.json','candidates/usb_fast_infer2/geometry_config.json','experiments/pl_pipeline_20261025/usable_v5_quad/pl3_usable_v5_quad_manifest_20261028.json']
   for name in paths:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);data={'tool_version':'2018.2'}
    if name==paths[-1]:data={'physical_bridge':{'physical':data}}
    p.write_text(json.dumps(data))
   with patch.object(startup,'PROJECT',root),patch.dict(sys.modules,{'check_current':SimpleNamespace(local_checks=lambda:{'passed':True})}):
    with self.assertRaisesRegex(RuntimeError,'2026.1'):startup.check_local()
if __name__=='__main__':unittest.main(verbosity=2)
