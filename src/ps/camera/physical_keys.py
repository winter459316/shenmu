"""Use the board's existing Linux gpio-keys device; never request GPIO ownership.

Fast profile: PL_KEY2 capture; PS_KEY1 results; PL_KEY1 live/filter cycle; PS_KEY2 frozen photo filters.
PL keys remain disabled until a bitstream actually connects their EMIO inputs.
No repeat/held/dropped event can create a new shutter action.
"""
import argparse,array,fcntl,http.client,json,os,select,signal,struct,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EVENT=struct.Struct('@llHHi')
KEYS={103:'ps_key1',108:'ps_key2',105:'pl_key1',106:'pl_key2'}

def request(path,body=None):
    c=http.client.HTTPConnection('192.168.137.2',8788,timeout=5,source_address=('127.0.0.1',0))
    try:
        data=None if body is None else json.dumps(body)
        c.request('GET' if body is None else 'POST',path,data,{} if body is None else {'Content-Type':'application/json'})
        r=c.getresponse();out=json.loads(r.read())
        if r.status>=400:raise RuntimeError(out.get('error','HTTP '+str(r.status)))
        return out
    finally:c.close()

class Actions:
    def __init__(self,call,pl_enabled=False,held=()):
        self.call=call;self.pl_enabled=pl_enabled;self.armed={k:k not in held for k in KEYS}
        self.counts={v:0 for v in KEYS.values()};self.last=None;self.dropped=False
    def resync(self,held):
        self.armed={k:k not in held for k in KEYS};self.dropped=False
    def event(self,event_type,code,value):
        if event_type==0 and code==3:self.dropped=True;return
        if self.dropped or event_type!=1 or code not in KEYS:return
        if value==0:self.armed[code]=True;return
        if value!=1 or not self.armed[code]:return
        self.armed[code]=False
        if code in (105,106) and not self.pl_enabled:return
        name=KEYS[code];self.counts[name]+=1
        self.last={'key':name,'monotonic':time.monotonic(),'result':'pending'}
        try:
            reply=self.call('/fast/key',{'key':name})
            self.last.update(reply)
        except Exception as exc:self.last.update(result='error',error=str(exc))

def held_keys(fd):
    bits=array.array('B',[0]*128)
    fcntl.ioctl(fd,(2<<30)|(len(bits)<<16)|(ord('E')<<8)|0x18,bits,True)
    return {k for k in KEYS if bits[k//8]&(1<<(k%8))}

def discover():
    mappings={}
    for node in Path('/proc/device-tree/keys').iterdir():
        if not node.is_dir() or not (node/'label').exists():continue
        label=(node/'label').read_bytes().rstrip(b'\0').decode()
        if label not in KEYS.values():continue
        code=struct.unpack('>I',(node/'linux,code').read_bytes())[0]
        gpio=struct.unpack('>III',(node/'gpios').read_bytes())
        mappings[label]=(code,gpio[1],gpio[2])
    expected={'ps_key1':(103,40,1),'ps_key2':(108,41,1),'pl_key1':(105,78,1),'pl_key2':(106,79,1)}
    if mappings!=expected:raise RuntimeError('gpio-keys mapping differs from the verified board')
    paths=[Path('/dev/input')/p.name for p in Path('/sys/class/input').glob('event*') if (p/'device/name').read_text().strip()=='keys']
    if len(paths)!=1:raise RuntimeError('Expected one gpio-keys input device')
    return paths[0],mappings

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pl',action='store_true');args=parser.parse_args()
    if args.pl:
        from hardware_catalog import loaded_variant
        assert loaded_variant(json.loads((ROOT/'loaded.json').read_text()))['pl_keys'],'PL keys are not connected in this bitstream'
    # During Fast restore, import/discovery preparation may overlap UVC reopen.
    # No input fd is opened and no key event is dispatched until preview is ready.
    gate=os.environ.get('USB_FAST_KEYS_GATE')
    if gate:
        gate=Path(gate);assert gate.parent.resolve()==ROOT.parent/'fast_infer2'
        deadline=time.monotonic()+10
        while not gate.exists():
            if time.monotonic()>deadline:raise TimeoutError('Preview resume gate did not open')
            time.sleep(.01)
        gate.unlink()
    lock=open(ROOT/'physical_keys.lock','a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path,mappings=discover();fd=os.open(str(path),os.O_RDONLY|os.O_NONBLOCK)
    assert EVENT.size==24,'Unexpected Linux input_event ABI'
    actions=Actions(request,args.pl,held_keys(fd));running=[True]
    def stop(*unused):running[0]=False
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    (ROOT/'physical_keys.pid').write_text(str(os.getpid()))
    next_status=0;last_count=-1
    try:
        while running[0]:
            readable,_,_=select.select([fd],[],[],0 if next_status==0 else .25)
            if readable:
                data=os.read(fd,EVENT.size*64)
                if not data or len(data)%EVENT.size:raise RuntimeError('Incomplete gpio-keys event stream')
                for off in range(0,len(data),EVENT.size):
                    _,_,kind,code,value=EVENT.unpack_from(data,off)
                    if actions.dropped and kind==0 and code==0:actions.resync(held_keys(fd))
                    else:actions.event(kind,code,value)
            count=sum(actions.counts.values())
            if time.monotonic()>=next_status or count!=last_count:
                status={'pid':os.getpid(),'device':str(path),'mapping':mappings,'pl_keys_enabled':args.pl,
                        'counts':actions.counts,'last':actions.last,'monotonic':time.monotonic(),'running':True}
                tmp=ROOT/'physical_keys_status.tmp';tmp.write_text(json.dumps(status));tmp.replace(ROOT/'physical_keys_status.json')
                if count!=last_count and actions.last:print(json.dumps(actions.last),flush=True)
                next_status=time.monotonic()+5;last_count=count
    finally:os.close(fd);lock.close()

if __name__=='__main__':main()
