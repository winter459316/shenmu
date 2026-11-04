"""Finite native-auto/manual exposure response test; restores controls in finally.

Run only before full_camera owns the UVC node. Does not trigger a project photo.
"""
import json,time
from pathlib import Path
import cv2
from auto_exposure import Controls,AUTO,ABSOLUTE,MAINS,meter
root=Path(__file__).resolve().parent
ctl=Controls('/dev/video0');old={k:ctl.get(k) for k in (AUTO,ABSOLUTE,MAINS)}
cap=cv2.VideoCapture('/dev/video0',cv2.CAP_V4L2);out=[]
try:
    assert cap.isOpened()
    cap.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,1280);cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    cap.set(cv2.CAP_PROP_FPS,30);cap.set(cv2.CAP_PROP_BUFFERSIZE,2)
    for value in (None,30,300,30):
        if value is None:ctl.set(AUTO,3)
        else:ctl.set(AUTO,1);ctl.set(ABSOLUTE,value)
        frames=0;began=time.monotonic();last=[]
        while time.monotonic()-began<2.5:
            ok,frame=cap.read();assert ok and frame.shape==(480,1280,3)
            frames+=1
            if time.monotonic()-began>2:last.append(meter(frame))
        row={'requested':value,'actual':ctl.get(ABSOLUTE),'fps':frames/(time.monotonic()-began),'meter':last[-1]}
        out.append(row);print(json.dumps(row),flush=True)
    (root/'exposure_probe.json').write_text(json.dumps(out,indent=2))
finally:
    ctl.set(AUTO,1);ctl.set(ABSOLUTE,old[ABSOLUTE]);ctl.set(AUTO,old[AUTO]);ctl.set(MAINS,old[MAINS])
    cap.release();ctl.close()
