"""Read-only diagnostics and strict physical-fence proof under a caller's lease."""
import time
from mmio_read44_20261027 import read_register
def status(io):
    return dict(status=read_register(io,4),fault=read_register(io,8),
                cycles=read_register(io,0x20)|(read_register(io,0x24)<<32))
def fenced_failure(io,check,*,samples=10,interval=.02):
    if type(samples) is not int or samples<3 or interval<0:raise ValueError('Insufficient fence observation')
    check()
    if read_register(io,0)!=0x31435046:raise RuntimeError('Qualified FPC1 identity lost')
    first=status(io)
    # Exact 0x18 = FAILED + physical DRAINED; all of READY, DONE, BUSY and
    # PENDING must be absent. Never infer a fence from software pending flags.
    if first['status']!=0x18 or not first['fault']:return None
    observed=[first]
    for _ in range(samples-1):
        time.sleep(interval);check();value=status(io)
        if value!=first:return None
        observed.append(value)
    return dict(physical_fence_verified=True,samples=observed,command_failed_not_completed=True)
def diagnostics(io,check):
    check()
    if read_register(io,0x28)!=0x44424731:raise RuntimeError('Qualified DBG1 observer identity lost')
    w=[read_register(io,0x40+4*i) for i in range(16)];check()
    return dict(words=w,last_reply_sequence=w[0],last_reply_tag=w[1],
        last_reply_generation=w[2]|(w[3]<<32),last_reply_status=w[4],
        weight_pending_bits=w[5]>>16,weight_row=(w[5]>>8)&255,weight_k=w[5]&255,
        next_weight_sequence=w[6],weight_command_tag=w[7],weight_generation=w[8]|(w[9]<<32),
        weight_address_word=w[10]|(w[11]<<32),gather_owner=(w[12]>>6)&3,gather_phase=(w[12]>>3)&7,
        core_state=(w[13]>>9)&31,producer_state=(w[13]>>14)&3,core_flags=w[13]&63,
        gather_fault_reason=w[14],core_error_status=w[15])
