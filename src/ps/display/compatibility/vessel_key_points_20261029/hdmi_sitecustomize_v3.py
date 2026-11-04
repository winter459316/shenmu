"""Opt-in display hooks. Qualified inference and camera source files are unchanged."""
import os,sys
from pathlib import Path
if os.environ.get('ZU4EV_HDMI_ADDON')=='hold_replay_v3':
    try:
        root=Path('/tmp/usb_stereo_probe');r=root/'fast_infer2';s=root/'usb320_hdmifps'
        for p in (root/'fast_board/deps',s,r):sys.path.insert(0,str(p))
        name=Path(sys.argv[0]).name
        if name=='full_camera.py':
            import fast_console
            from vessel_photo import VesselPhotoViews,MODES
            fast_console.PhotoViews=VesselPhotoViews
            fast_console.MODES=MODES
            from replay_console_v1 import ReplayConsole
            fast_console.FastConsole=ReplayConsole
        elif name=='infer_worker_pl3_v5_quad.py':
            import pl3_execute_v5_quad
            from hold_client_v2 import call
            Original=pl3_execute_v5_quad.PhysicalBridge
            class DisplayBridge(Original):
                def begin(self):
                    job=self.evidence_root.name
                    call(job,'stop');super().begin();call(job,'start','pl3')
                def restore_pl2(self):
                    job=self.evidence_root.name
                    call(job,'stop');super().restore_pl2();call(job,'start','pl2')
            pl3_execute_v5_quad.PhysicalBridge=DisplayBridge
    except BaseException:
        import traceback
        traceback.print_exc();os._exit(70)
