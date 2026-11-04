import http.client,json,time
import cv2,numpy as np
from shared_preview import SharedPreview
from switch_320_board import request
saved=request(8788,'/status')['mode'];request(8788,'/preview/mode',{'mode':'color'})
try:
    c=http.client.HTTPConnection('192.168.137.2',8788,source_address=('127.0.0.1',0))
    c.request('GET','/snapshot.png');r=c.getresponse();assert r.status==200
    frame=cv2.imdecode(np.frombuffer(r.read(),np.uint8),cv2.IMREAD_COLOR);c.close()
    np.save('profile_native.npy',frame)
    p=SharedPreview();rows=[]
    for threads in (1,2,3):
        cv2.setNumThreads(threads);times=[]
        for i in range(6):
            t=time.monotonic()
            eyes=[cv2.resize(frame[:,e*640:(e+1)*640],(320,360),interpolation=cv2.INTER_AREA) for e in (0,1)]
            t1=time.monotonic();grid=p.rectifier.rectified_grid(np.concatenate(eyes,axis=1));t2=time.monotonic()
            small=cv2.resize(grid,(640,240));big=cv2.resize(grid,(1280,480));t3=time.monotonic()
            cv2.imencode('.jpg',small,[cv2.IMWRITE_JPEG_QUALITY,75]);t4=time.monotonic()
            times.append([(t1-t)*1000,(t2-t1)*1000,(t3-t2)*1000,(t4-t3)*1000])
        rows.append({'threads':threads,'ms_resize_input_remap_resize_output_jpeg':np.mean(times,axis=0).tolist()})
    print(json.dumps(rows),flush=True)
finally:request(8788,'/preview/mode',{'mode':saved})
