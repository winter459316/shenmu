"""Explicit, volatile HDMI promotion with verified stable rollback.

Without --apply this only checks files and lists service owners. It never
stops services, opens /dev/mem, initializes PS, or writes boot storage.
The caller must stop the camera/key services before an authorized --apply.
"""
import argparse,hashlib,json,os,time
from pathlib import Path
from hardware_catalog import STABLE_SHA,HDMI_V1_SHA,loaded_variant

ROOT=Path(__file__).resolve().parent
IDENTITIES=(('sgm',0x55534738),('images',0x55494632),
            ('geometry',0x55474532),('completion',0x43475032))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic_write(path,data):
    temp=path.with_name(path.name+'.pending')
    with temp.open('wb') as output:
        output.write(data);output.flush();os.fsync(output.fileno())
    temp.replace(path)

def validate_files(root):
    proof=json.loads((root/'hdmi_hardware_verified.json').read_text())
    board=json.loads((root/'hdmi_full_verified.json').read_text())
    pc=json.loads((root/'hdmi_full_pc_verified.json').read_text())
    for key in ('timing_passed','cdc_review_passed','key_synchronizers_verified','board_test_passed'):
        assert proof.get(key) is True,'Missing hardware proof: '+key
    for key in ('passed','stable_restored','hdmi_drained','held_photo_unchanged'):
        assert board.get(key) is True,'Missing board proof: '+key
    assert pc.get('passed') is True and pc.get('array_count')==51
    assert len(pc['byte_exact_arrays'])==51 and all(v is True for v in pc['byte_exact_arrays'].values())
    assert proof['board_test_sha256']==digest(root/'hdmi_full_verified.json')==pc['board_report_sha256']
    assert proof['independent_verification_sha256']==digest(root/'hdmi_full_pc_verified.json')
    assert proof['bin_sha256']==board['candidate_sha256']==HDMI_V1_SHA
    assert digest(root/'hdmi_v1.bit.bin')==HDMI_V1_SHA
    assert digest(root/'usb_full.bit.bin')==STABLE_SHA,'Verified rollback image is required'
    previous=(root/'loaded.json').read_bytes();loaded=json.loads(previous)
    loaded_variant(loaded)
    assert loaded['sha256']==STABLE_SHA,'This promotion starts only from the stable image'
    assert not (root/'dma.fault').exists(),'Unresolved compute DMA fault'
    assert not (root/'hdmi.fault').exists(),'Unresolved HDMI DMA fault'
    return previous

def service_owners(proc=Path('/proc')):
    result=[]
    for item in proc.iterdir():
        if not item.name.isdigit() or int(item.name)==os.getpid():continue
        try:
            args=(item/'cmdline').read_bytes().split(b'\0')
            scripts={Path(x.decode(errors='replace')).name for x in args if x}
            matched=sorted(scripts&{'full_camera.py','physical_keys.py'})
            if matched:result.append({'pid':int(item.name),'scripts':matched})
        except (FileNotFoundError,PermissionError,ProcessLookupError):continue
    return result

def promote(backend,previous):
    """Transaction shared with offline fault-injection tests.

    The caller owns both locks throughout. Only identity/calibration commands
    run here; neither compute DMA nor HDMI scanout is started by this loader.
    """
    original=json.loads(previous)
    report={'passed':False,'services_started':False,'stable_restored':False,
            'rollback_attempted':False,'hardware_change_attempted':False}
    backend.assert_quiet()
    began=time.monotonic()
    try:
        pending=dict(original,state='configuring',target_sha256=HDMI_V1_SHA)
        backend.metadata(json.dumps(pending).encode())
        report['hardware_change_attempted']=True
        backend.load('hdmi_v1.bit.bin')
        backend.verify(0x53574E34)
        loaded=dict(original,sha256=HDMI_V1_SHA,load_seconds=time.monotonic()-began,
                    temporary_hardware_test=False)
        backend.metadata(json.dumps(loaded).encode())
        report.update(passed=True,loaded_sha256=HDMI_V1_SHA)
    except Exception as exc:
        report['error']=str(exc) or repr(exc)
        if not report['hardware_change_attempted']:
            backend.metadata(previous)
            report['stable_restored']=True
        else:
            try:
                report['rollback_attempted']=True
                backend.load('usb_full.bit.bin')
                backend.verify(None)
                backend.metadata(previous)
                report['stable_restored']=True
            except Exception as rollback:
                report['rollback_error']=str(rollback) or repr(rollback)
                unknown=dict(original,state='recovery_required',sha256=None)
                backend.metadata(json.dumps(unknown).encode())
    return report

class Hardware:
    def __init__(self,root,arena):
        self.root=root;self.arena=arena
        self.firmware_path=Path('/sys/module/firmware_class/parameters/path')
        self.old_path=self.firmware_path.read_text()
        self.old_flags=Path('/sys/class/fpga_manager/fpga0/flags').read_text()
    def assert_quiet(self):
        assert not service_owners(),'Stop camera/key services before reconfiguration'
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
        assert all(self.arena.read(k,0)&4 for k in self.arena.controls),'Outstanding compute DMA'
    def metadata(self,data):atomic_write(self.root/'loaded.json',data)
    def load(self,filename):
        # Both files have been hashed before taking action. Neither image
        # starts a bus master until software explicitly starts its DMA.
        expected={'hdmi_v1.bit.bin':HDMI_V1_SHA,'usb_full.bit.bin':STABLE_SHA}
        assert digest(self.root/filename)==expected[filename]
        self.firmware_path.write_text(str(self.root))
        Path('/sys/class/fpga_manager/fpga0/flags').write_text('0')
        Path('/sys/class/fpga_manager/fpga0/firmware').write_text(filename)
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
    def identity(self,name,operation):
        # Restricted to commands that never touch DDR. A failed identity can
        # be recovered by loading stable hardware without aborting compute DMA.
        assert operation in (0,3)
        assert self.arena.read(name,0)&4,'Core is not idle: '+name
        self.arena.write(name,0x20,operation);self.arena.fence()
        self.arena.write(name,0,1);self.arena.fence();deadline=time.monotonic()+2
        while not self.arena.read(name,0)&2:
            if time.monotonic()>deadline:raise TimeoutError('Identity timeout: '+name)
            time.sleep(.001)
        self.arena.fence();return self.arena.read(name,0x10)
    def verify(self,revision):
        from board_dma import TAG
        for name,value in IDENTITIES:assert self.identity(name,0)==value,'Core identity: '+name
        for name in ('images','geometry'):assert self.identity(name,3)==TAG,'Calibration: '+name
        if revision is not None:assert self.identity('sgm',3)==revision,'SGM revision'
        assert all(self.arena.read(k,0)&4 for k in self.arena.controls),'Identity command not idle'
    def restore_parameters(self):
        try:self.firmware_path.write_text(self.old_path)
        finally:Path('/sys/class/fpga_manager/fpga0/flags').write_text(self.old_flags)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Reconfigure PL; requires authorized service shutdown first')
    args=parser.parse_args()
    previous=validate_files(ROOT);owners=service_owners()
    if not args.apply:
        print(json.dumps({'files_verified':True,'read_only':True,'service_owners':owners,
                          'ready_for_apply':not owners,'restart_authorization_required':True}));return
    assert not owners,'Stop camera/key services before --apply'
    import fcntl
    from board_dma import Arena
    with (ROOT/'hdmi.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        arena=Arena(True);hardware=None;report=None
        try:
            assert validate_files(ROOT)==previous
            hardware=Hardware(ROOT,arena)
            report=promote(hardware,previous)
        finally:
            try:
                if hardware is not None:hardware.restore_parameters()
            except Exception as exc:
                if report is None:raise
                report.update(passed=False,parameter_restore_error=str(exc))
            finally:arena.close()
        atomic_write(ROOT/'hdmi_activation.json',json.dumps(report,indent=2).encode())
        print(json.dumps(report))
        if not report['passed']:raise RuntimeError('HDMI activation failed; inspect hdmi_activation.json before starting services')

if __name__=='__main__':main()
