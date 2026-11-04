import os,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
gcc=Path('D:/xilinx/SDK/2018.2/gnu/aarch64/nt/aarch64-linux/bin/aarch64-linux-gnu-gcc.exe')
env=dict(os.environ);env['PATH']=str(gcc.parent)+os.pathsep+env['PATH']
subprocess.run([str(gcc),'-O3','-fPIC','-shared','-std=c99','-pthread','-Wall','-Wextra','-Werror',
    str(ROOT/'preview_native.c'),'-o',str(ROOT/'preview_native.so')],env=env,check=True)
print(hashlib.sha256((ROOT/'preview_native.so').read_bytes()).hexdigest())
