"""Build the isolated 32-bit HDMI register accessor for AArch64 Linux."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
gcc=Path('D:/xilinx/SDK/2018.2/gnu/aarch64/nt/aarch64-linux/bin/aarch64-linux-gnu-gcc.exe')
env=dict(os.environ);env['PATH']=str(gcc.parent)+os.pathsep+env['PATH']
subprocess.run([str(gcc),'-O2','-fPIC','-shared','-std=c11','-Wall','-Wextra','-Werror',
                '-o',str(ROOT/'hdmi_mmio.so'),str(ROOT/'hdmi_mmio.c')],env=env,check=True)
