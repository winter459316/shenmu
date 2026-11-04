"""Load the accepted 320 image and start its services after a reserved RAM boot.

Run only on a fresh deployment with no camera owners or previous loaded.json.
Image algorithms are unchanged; removed legacy compute APIs are guarded.
"""
import fcntl, hashlib, json, mmap, os, struct, subprocess, time
from pathlib import Path
from board_dma import Arena, TAG, reservation
from hardware_catalog import HDMI_SECTION_SHA as HDMI_TRIM_SHA
from preview_hardware import check_preview
from switch_320_board import owners, program, request

ROOT = Path(__file__).resolve().parent

def main():
    assert not owners(), 'An existing camera/key service must be handled separately'
    assert not (ROOT/'loaded.json').exists(), 'Use the active-runtime recovery procedure'
    reservation()
    assert not list(Path('/sys/bus/platform/devices').glob('a0*/driver'))
    manifest=json.loads((ROOT/'startup_payload_sha256.json').read_text())
    for name, expected in manifest.items():
        assert Path(name).name==name
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, name
    proof=json.loads((ROOT/'hardware_320_verified.json').read_text())
    assert all(proof[k] for k in ('timing_passed','cdc_review_passed','keys_passed','hls_passed'))
    assert proof['sha256']==HDMI_TRIM_SHA
    assert hashlib.sha256((ROOT/'usb320.bit.bin').read_bytes()).hexdigest()==HDMI_TRIM_SHA
    from full_runtime import FullRuntime
    FullRuntime()  # Validate Python/native dependencies and bound calibration first.
    clock=Path('/sys/kernel/debug/clk/clk_summary').read_text()
    row=next(s.split() for s in clock.splitlines() if s.split() and s.split()[0]=='pl0_ref')
    rate=int(row[4]);assert 99000000<=rate<=100000000, rate
    lockdir=ROOT.parent/'full_v2';lockdir.mkdir(exist_ok=True)
    with (lockdir/'hdmi.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        a=Arena(False)
        try:
            def reg(address):
                with mmap.mmap(a.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=address&~4095) as m:
                    return struct.unpack_from('<I',m,address&4095)[0]
            widths={'hpm0':reg(0xFD615000),'hp2_read':reg(0xFD3A0000),'hp2_write':reg(0xFD3A0014)}
            assert widths['hpm0']&0x300==0x200, widths
            assert widths['hp2_read']&3==0 and widths['hp2_write']&3==0, widths
            began=time.monotonic();program(ROOT,'usb320.bit.bin')
            check_preview(a)
            loaded={'version':'usb_full_v2','state':'operating','sha256':HDMI_TRIM_SHA,
                    'load_seconds':time.monotonic()-began,'clock_hz':rate,'width_registers':widths,
                    'volatile':True,'dma_reservation':reservation(),'cold_start_verified':True}
            (ROOT/'loaded.json').write_text(json.dumps(loaded,indent=2))
        finally:a.close()
    env=os.environ.copy()
    env.update(USB_DEVICE='/dev/video0',USB_HDMI='1',USB_RESTORE_HELD='1',USB_SURFACE_NATIVE='1',
               USB_MESH_NATIVE='1',USB_HOLES_PARALLEL='1',USB_ARCHIVE_STORED='1',
               OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
    def launch(name,args):
        with (ROOT/(name+'.log')).open('ab',buffering=0) as log:
            p=subprocess.Popen(['python3','-u',str(ROOT/(name+'.py'))]+args,cwd=str(ROOT),env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        (ROOT/(name+'.pid')).write_text(str(p.pid));return p
    camera=launch('full_camera',[]);deadline=time.monotonic()+25
    while time.monotonic()<deadline and camera.poll() is None:
        try:
            s=request(8788,'/status');h=request(8788,'/hdmi/status')
            if not s['error'] and s['age_seconds']<2 and h['frames']>=2 and not h['error']:break
        except OSError:pass
        time.sleep(.2)
    else:raise RuntimeError('Camera/HDMI did not become ready; inspect full_camera.log')
    keys=launch('physical_keys',['--pl']);deadline=time.monotonic()+6
    while time.monotonic()<deadline and keys.poll() is None:
        path=ROOT/'physical_keys_status.json'
        if path.exists() and json.loads(path.read_text()).get('pid')==keys.pid:break
        time.sleep(.2)
    else:raise RuntimeError('Keys did not become ready; inspect physical_keys.log')
    result={'passed':True,'camera_pid':camera.pid,'keys_pid':keys.pid,'camera':s,'hdmi':h,'loaded':loaded}
    (ROOT/'cold_start_verified.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
