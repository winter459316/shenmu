"""Display-only viewport shared by the HDMI consumer and browser controls."""
import math,threading,time
import cv2
LOCK=threading.Lock()
view=dict(scale=1.0,cx=.5,cy=.5,revision=0)
applied={}
def status():
    with LOCK:return dict(view,applied=dict(applied))
def set_view(args):
    if set(args)!={'scale','cx','cy'}:raise ValueError('Invalid preview viewport')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in args.values()):raise ValueError('Invalid viewport numbers')
    scale=float(args['scale'])
    if not 1<=scale<=6 or not 0<=args['cx']<=1 or not 0<=args['cy']<=1:raise ValueError('Viewport outside limits')
    half=.5/scale
    with LOCK:
        view.update(scale=scale,cx=max(half,min(1-half,args['cx'])),cy=max(half,min(1-half,args['cy'])),revision=view['revision']+1)
    return status()
def crop_rect(width,height,v):
    w=max(1,int(width/v['scale']+.5));h=max(1,int(height/v['scale']+.5))
    x=max(0,min(width-w,int(v['cx']*width-w/2+.5)))
    y=max(0,min(height-h,int(v['cy']*height-h/2+.5)))
    return x,y,w,h
def apply(frame,v,dst=None):
    height,width=frame.shape[:2];x,y,w,h=crop_rect(width,height,v)
    if (w,h)==(width,height):
        out=frame if dst is None else dst
        if dst is not None:dst[:]=frame
    else:out=cv2.resize(frame[y:y+h,x:x+w],(width,height),dst=dst,interpolation=cv2.INTER_NEAREST)
    with LOCK:applied.update(revision=v['revision'],roi=[x,y,w,h],size=[width,height],stamp=time.monotonic())
    return out
