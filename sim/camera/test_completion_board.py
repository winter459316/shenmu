"""One saved-photo CPU/PL comparison. No camera access or shutter loop."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from board_dma import Arena
from board_completion import complete,CompletionCancelled,N
ROOT=Path(__file__).resolve().parent
def main():
    with np.load(ROOT/'hardware_case.npz') as z:case={k:z[k] for k in z.files}
    domain=((case['maps0']>>42)&1).astype(bool)
    before=hashlib.sha256(case['q'].tobytes()).hexdigest()
    last=[0]
    def progress(phase,stats):
        now=time.monotonic()
        if now-last[0]>2:
            print(phase,stats['phase'],stats['iterations'],round(stats['elapsed_seconds'],2),flush=True);last[0]=now
    reference,origins,ps=complete(case['rect0'],case['q'],case['valid'],domain,use_pl=False,progress=progress)
    print('CPU_DONE',json.dumps(ps),flush=True)
    a=Arena(True)
    guards=[24*N*16-4096,26*N*16];saved=[a.memory[o:o+4096] for o in guards]
    pattern=bytes((i*31+7)%256 for i in range(4096))
    try:
        for o in guards:a.memory[o:o+4096]=pattern
        actual,actual_origins,pl=complete(case['rect0'],case['q'],case['valid'],domain,a,True,progress)
        print('PL_DONE',json.dumps(pl),flush=True)
        assert np.array_equal(actual,reference),'CPU/PL completed Q4 differs'
        assert np.array_equal(actual_origins,origins),'CPU/PL provenance differs'
        for key in ('iterations','converged','residual_ppm','measured','rejected','local','inferred','extrapolated'):
            assert pl[key]==ps[key],(key,pl[key],ps[key])
        assert pl['cg']['commands']>0 and pl['cg']['multiplies']==pl['iterations']
        assert pl['cg']['updates']==pl['iterations'] and pl['cg']['directions']==pl['iterations']-1
        assert all(a.memory[o:o+4096]==pattern for o in guards),'CG DMA crossed arena boundary'
        assert before==hashlib.sha256(case['q'].tobytes()).hexdigest()
        cancelled=False
        try:complete(case['rect0'],case['q'],case['valid'],domain,a,True,cancel=lambda:True)
        except CompletionCancelled:cancelled=True
        assert cancelled
        identity,_=a.command('completion',{0x20:0});assert identity==0x43475032
        report={'passed':True,'case_sha256':hashlib.sha256((ROOT/'hardware_case.npz').read_bytes()).hexdigest(),
                'library_sha256':hashlib.sha256((ROOT/'usb_completion.so').read_bytes()).hexdigest(),
                'shape':[480,640],'completed_q4_exact':True,'origins_exact':True,'convergence_exact':True,
                'original_immutable':True,'dma_guards_unchanged':True,'early_cancel_then_core_identity':True,
                'cpu':ps,'pl':pl}
        np.savez_compressed(ROOT/'completion_result.npz',q4=actual,origin=actual_origins,cpu_q4=reference,cpu_origin=origins,domain=domain,
                            metadata_json=np.frombuffer(json.dumps(report).encode(),np.uint8))
        (ROOT/'completion_verified.json').write_text(json.dumps(report,indent=2));print('COMPLETION_PASS',json.dumps(report),flush=True)
    finally:
        for o,s in zip(guards,saved):a.memory[o:o+4096]=s
        a.close()
if __name__=='__main__':main()
