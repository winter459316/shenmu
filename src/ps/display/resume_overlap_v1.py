from pause_preview_board import *
def resume(saved):
    timings={};started=time.monotonic()
    lease=saved.get('pause_lease',{});camera=saved['owners']['full_camera.py']
    if lease.get('frozen'):
        assert_frozen_lease(saved)
        regs=lease.get('registers')
        if regs:
            with MMIO() as io:
                d={int(k):v for k,v in regs['dma'].items()};v={int(k):v for k,v in regs['vtc'].items()}
                io.write(io.dma,0,0);io.wait(4,1,1);io.write(io.dma,0,4);io.wait(0,4,0)
                io.write(io.vtc,0,0)
                for off in VIDEO_REGS:io.write(io.vtc,off,v[off])
                io.write(io.vtc,0,v[0]);io.write(io.dma,4,0xff0);io.write(io.dma,0,d[0]);io.wait(4,1,0)
                for off in (0x5c,0x60,0x58,0x54):io.write(io.dma,off,d[off])
                io.write(io.dma,0x50,d[0x50]);park=d[0x28]&0xffff
                io.write(io.dma,0x28,park);io.wait(0x28,0x1f0000,(park&0x1f)<<16)
        (S/'loaded.json').write_text(saved['loaded'])
        os.kill(camera['pid'],signal.SIGCONT);wait_state(camera,False)
    timings['restore_mmio_and_thaw']=time.monotonic()-started;started=time.monotonic()
    key_process=None;gate=None
    if lease.get('keys_stopped'):
        assert set(h.owners())=={'full_camera.py'}
        key=saved['owners']['physical_keys.py'];env=key['env'].copy()
        gate=R/('keys_resume_'+str(os.getpid())+'.gate');assert not gate.exists()
        env['USB_FAST_KEYS_GATE']=str(gate)
        with (S/'physical_keys_fast_resume.log').open('ab',buffering=0) as log:
            key_process=subprocess.Popen(key['cmd'],cwd=key['cwd'],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    h.request(8788,'/standby',{'enabled':saved['standby']})
    for _ in range(80):
        c=h.request(8788,'/status');video=h.request(8788,'/hdmi/status')
        if not c['error'] and not c.get('preview_error') and not c.get('jpeg_error') and c['age_seconds']<.3 and not video['error'] and video['source']=='preview':break
        time.sleep(.05)
    else:
        # The original bit is already restored. A failed UVC reopen may safely use
        # the proven full-service restart; never leave a completed photo stranded.
        assert not json.loads((R/'configuration_state.json').read_text())['new']
        assert not (S/'hdmi.fault').exists()
        if key_process is not None and key_process.poll() is None:
            key_process.terminate();key_process.wait(timeout=3)
        if gate is not None and gate.exists():gate.unlink()
        current=h.owners();assert set(current)=={'full_camera.py'} and current['full_camera.py']==camera
        h.stop(current);h.restore_services(saved)
        report=json.loads((R/'stable_restored.json').read_text())
        report.update(camera_process_preserved=False,preview_restart_fallback=True)
        (R/'stable_restored.json').write_text(json.dumps(report,indent=2))
        return report
    timings['uvc_reopen_and_fresh_preview']=time.monotonic()-started;started=time.monotonic()
    state=h.request(8788,'/stereo/status')
    assert state['result_id']==saved['held']['job_id'] and state['metadata']['package_sha256']==saved['held']['sha256']
    if key_process is not None:
        gate.write_text('preview_ready')
        p=key_process
        for _ in range(80):
            assert p.poll() is None
            status=json.loads((S/'physical_keys_status.json').read_text())
            if status.get('pid')==p.pid:break
            time.sleep(.01)
        else:raise RuntimeError('Key service did not recover')
    owners=h.owners();assert set(owners)=={'full_camera.py','physical_keys.py'}
    assert owners['full_camera.py']==camera
    timings['keys_and_ownership_verification']=time.monotonic()-started
    report=dict(resume_breakdown_seconds=timings,passed=True,held=saved['held'],camera_pid=camera['pid'],keys_pid=owners['physical_keys.py']['pid'],camera_process_preserved=True,preview=c,hdmi=video,stable_bitstream_sha256=h.OLD_SHA)
    (R/'stable_restored.json').write_text(json.dumps(report,indent=2))
    print('PREVIEW_RESUMED_SAME_CAMERA',camera['pid'],flush=True)
    return report
