"""Recompute the paired-run medians from saved evidence; never invoke hardware."""
from pathlib import Path
import csv,json,statistics,sys
ROOT=Path(__file__).resolve().parents[1]
def rows():
    data=json.loads((ROOT/'sim/results/benchmark/store2_benchmark.json').read_text())['results']
    condition='ZU4EV; identical saved stereo input; 320x360; 2 iterations; 110 MHz versus 115 MHz; two runs per group'
    for key,label in [('conv_device_seconds','convolution_core'),('forward_seconds','network_forward'),('total_seconds','board_total')]:
        before=statistics.median(data[n][key] for n in ('baseline0','baseline1'))
        after=statistics.median(data[n][key] for n in ('store20','store21'))
        yield {'metric':label,'baseline_seconds':before,'optimized_seconds':after,'reduction_percent':(before-after)/before*100,'conditions':condition,'evidence':'sim/results/benchmark/store2_benchmark.json'}
if __name__=='__main__':
    data=list(rows());writer=csv.DictWriter(sys.stdout,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
