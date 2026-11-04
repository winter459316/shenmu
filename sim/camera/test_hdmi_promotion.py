"""Offline promotion fault injection; no board, sysfs, MMIO, or process control."""
import contextlib,hashlib,io,json,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import load_verified_hdmi as loader

ROOT=Path(__file__).resolve().parent
PREVIOUS=json.dumps({'version':'usb_full_v2','state':'operating',
                     'sha256':loader.STABLE_SHA,'clock_hz':99999999},indent=2).encode()

class Backend:
    def __init__(self,failures=()):
        self.failures=set(failures);self.events=[];self.image='stable';self.saved=PREVIOUS
    def step(self,name):
        self.events.append(name)
        if name in self.failures:raise RuntimeError('Injected '+name)
    def assert_quiet(self):self.step('quiet')
    def load(self,name):
        self.image='candidate' if name=='hdmi_v1.bit.bin' else 'stable'
        self.step('load_'+self.image)
    def verify(self,revision):
        assert revision==(0x53574E34 if self.image=='candidate' else None)
        self.step('verify_'+self.image)
    def metadata(self,data):
        value=json.loads(data)
        if value['state']=='configuring':name='prepare'
        elif value['state']=='recovery_required':name='unknown'
        elif value['sha256']==loader.HDMI_V1_SHA:name='commit'
        else:name='restore'
        self.step(name);self.saved=data

def reject(call):
    try:call()
    except (AssertionError,ValueError,RuntimeError):return
    raise AssertionError('Invalid operation was accepted')

def main():
    checks={}
    b=Backend();report=loader.promote(b,PREVIOUS)
    assert report['passed'] and not report['rollback_attempted'] and b.events==[
        'quiet','prepare','load_candidate','verify_candidate','commit']
    assert json.loads(b.saved)['sha256']==loader.HDMI_V1_SHA
    checks['success_commits_only_after_identity']=True
    for fail in ('load_candidate','verify_candidate','commit'):
        b=Backend((fail,));r=loader.promote(b,PREVIOUS)
        assert not r['passed'] and r['stable_restored'] and r['rollback_attempted']
        assert b.saved==PREVIOUS and b.events[-3:]==['load_stable','verify_stable','restore']
        checks[fail+'_restores_exact_previous_metadata']=True
    for fail in ('load_stable','verify_stable'):
        b=Backend(('verify_candidate',fail));r=loader.promote(b,PREVIOUS)
        assert not r['passed'] and not r['stable_restored'] and r['rollback_error']
        assert json.loads(b.saved)['state']=='recovery_required' and json.loads(b.saved)['sha256'] is None
        checks[fail+'_does_not_claim_stable']=True
    b=Backend(('prepare',));r=loader.promote(b,PREVIOUS)
    assert not r['hardware_change_attempted'] and not any(v.startswith('load_') for v in b.events)
    assert b.saved==PREVIOUS;checks['metadata_preparation_failure_leaves_hardware_untouched']=True
    b=Backend(('quiet',));reject(lambda:loader.promote(b,PREVIOUS))
    assert b.events==['quiet'] and b.saved==PREVIOUS
    checks['busy_preflight_has_no_mutation']=True
    with tempfile.TemporaryDirectory(prefix='hdmi_promotion_test_') as temp:
        root=Path(temp)
        for name in ('hdmi_v1.bit.bin','usb_full.bit.bin','hdmi_hardware_verified.json'):
            shutil.copyfile(ROOT/name,root/name)
        for name in ('hdmi_full_verified.json','hdmi_full_pc_verified.json'):
            shutil.copyfile(ROOT/'board_evidence'/name,root/name)
        (root/'loaded.json').write_bytes(PREVIOUS)
        assert loader.validate_files(root)==PREVIOUS
        checks['real_candidate_and_evidence_hashes_verified']=True
        for name in ('dma.fault','hdmi.fault'):
            (root/name).write_text('unresolved')
            reject(lambda:loader.validate_files(root));(root/name).unlink()
            checks[name+'_refuses_activation']=True
        pc=root/'hdmi_full_pc_verified.json';original=pc.read_bytes()
        pc.write_bytes(original+b' ');reject(lambda:loader.validate_files(root));pc.write_bytes(original)
        checks['changed_evidence_rejected']=True
        stable=root/'usb_full.bit.bin';original=stable.read_bytes()
        stable.write_bytes(bytes([original[0]^1])+original[1:])
        reject(lambda:loader.validate_files(root));stable.write_bytes(original)
        checks['damaged_rollback_bitstream_rejected']=True
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        out=io.StringIO()
        with patch.object(loader,'ROOT',root),patch.object(loader,'service_owners',return_value=[{'pid':123,'scripts':['full_camera.py']}]),patch.object(loader,'Hardware',side_effect=AssertionError('MMIO should not open')),patch.object(sys,'argv',['load_verified_hdmi.py']),contextlib.redirect_stdout(out):
            loader.main()
        status=json.loads(out.getvalue());assert status['read_only'] and not status['ready_for_apply']
        assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
        checks['default_cli_read_only_no_hardware_or_file_mutation']=True
        process_root=root/'proc';process_root.mkdir()
        for pid,command in ((123,b'python3\0/tmp/full_camera.py\0'),(124,b'python3\0physical_keys.py\0'),(125,b'python3\0unrelated.py\0')):
            folder=process_root/str(pid);folder.mkdir();(folder/'cmdline').write_bytes(command)
        assert [x['pid'] for x in sorted(loader.service_owners(process_root),key=lambda x:x['pid'])]==[123,124]
        checks['absolute_and_relative_service_arguments_detected']=True
    report={'passed':True,'physical_hardware_used':False,'services_restarted':False,'cases':checks,
            'loader_sha256':hashlib.sha256((ROOT/'load_verified_hdmi.py').read_bytes()).hexdigest(),
            'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (ROOT/'board_evidence'/'hdmi_promotion_software_verified.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))

if __name__=='__main__':main()
