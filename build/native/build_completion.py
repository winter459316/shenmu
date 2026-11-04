"""Build the isolated Linux completion library; never edits old releases."""
import os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
GCC=Path('D:/xilinx/SDK/2018.2/gnu/aarch64/nt/aarch64-linux/bin/aarch64-linux-gnu-gcc.exe')
env=dict(os.environ);env['PATH']=str(GCC.parent)+os.pathsep+env['PATH']
subprocess.run([str(GCC),'-O3','-ffp-contract=off','-fPIC','-shared','-std=c11',
                '-Wall','-Wextra','-o',str(ROOT/'usb_completion.so'),
                str(ROOT/'hr_completion.c'),str(ROOT/'linux_completion_dma.c'),'-lm'],
               env=env,check=True)
