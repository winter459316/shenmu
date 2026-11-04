"""Apply relocation/serial adapters in memory; never edit the qualified files."""
from pathlib import Path
import json, runpy, sys

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parent

def relocate(value):
    text=str(value).replace('\\','/')
    marker='/zu4ev_stereo/'
    if marker in text:
        return PROJECT/text.split(marker,1)[1]
    p=Path(value)
    return p if p.is_absolute() else PROJECT/p

def configure_serial():
    sys.path.insert(0,str(PROJECT/'experiments/usb_camera_20261016/deps'))
    import serial
    if getattr(serial,'_shenmu_adapted',False): return
    original=serial.Serial
    target=json.loads((HERE/'config.json').read_text(encoding='utf-8-sig'))['serial_port']
    def adapted(port=None,*args,**kwargs):
        return original(target if str(port).upper()=='COM3' else port,*args,**kwargs)
    serial.Serial=adapted
    serial._shenmu_adapted=True

def run_script(path,args=()):
    path=Path(path).resolve()
    old_argv=sys.argv[:]
    sys.argv=[str(path),*args]
    sys.path.insert(0,str(path.parent))
    configure_serial()
    try:
        source=path.read_text(encoding='utf8')
        if path.name=='stage.py' and path.parent.name=='usable_v5_quad':
            source=source.replace('files={n:Path(p) for n,p in', 'files={n:relocate(p) for n,p in')
        if path.name=='select_mode.py' and path.parent.name=='usable_v5_quad':
            old="subprocess.run([sys.executable,'-X','utf8',str(U/'stage.py')],check=True)"
            assert old in source
            source=source.replace(old,"run_script(U/'stage.py')")
        scope={'__name__':'__main__','__file__':str(path),'relocate':relocate,'run_script':run_script}
        exec(compile(source,str(path),'exec'),scope)
    finally:
        sys.argv=old_argv

if __name__=='__main__':
    run_script(sys.argv[1],sys.argv[2:])
