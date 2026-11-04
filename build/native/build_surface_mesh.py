"""Build a separate exact-FP32 A53 mesh library; preserved plane library untouched."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
gcc=Path('D:/xilinx/SDK/2018.2/gnu/aarch64/nt/aarch64-linux/bin/aarch64-linux-gnu-gcc.exe')
env=dict(os.environ);env['PATH']=str(gcc.parent)+os.pathsep+env['PATH']
subprocess.run([str(gcc),'-O3','-ffp-contract=off','-fno-fast-math','-fPIC','-shared','-std=c11','-pthread',
    '-Wall','-Wextra','-Werror','-o',str(ROOT/'libsurface_mesh.so'),str(ROOT/'surface_mesh_native.c'),'-lm'],env=env,check=True)
