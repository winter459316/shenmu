"""Exact-plan batch dispatch to an externally owned FPC1 register transport.

No /dev/mem mapping, image loading, lock acquisition/release or convolution.
The caller keeps the qualified image, register page and exclusive DMA lease
alive throughout execution, including every error. Bias/activation follow on PS.
"""
import ctypes as C


class IO(C.Structure):
    _fields_=[(name,C.c_void_p) for name in ('opaque','read32','write32','barrier','now_ns','pause')]


class State(C.Structure):
    _fields_=[(name,C.c_uint64) for name in ('pending_epoch','last_epoch','active_cycles')]
    _fields_ += [(name,C.c_uint32) for name in ('pending_tag','pending','completed','status','fault','blocked')]


class NativeFailure(RuntimeError):
    def __init__(self,code,state):
        super().__init__('Native FPC1 dispatch failed: rc=%d status=%#x fault=%#x; ownership retained'
                         %(code,state.status,state.fault))
        self.code=code
        self.pending_epoch=state.pending_epoch
        self.pending_tag=state.pending_tag
        self.transport_drained=bool(state.status&16)


class NativeControl:
    def __init__(self,library,io,arena,*,assert_owned,keepalive=()):
        if not isinstance(io,IO) or not all(getattr(io,name) for name in
                                          ('read32','write32','barrier','now_ns','pause')):
            raise ValueError('Missing native register transport callbacks')
        if not (0<=arena[0]<arena[1]<1<<64):
            raise ValueError('Invalid caller-owned arena')
        self.lib=C.CDLL(str(library))
        self.lib.fpc1_run_batch.argtypes=[C.POINTER(IO),C.POINTER(State),C.POINTER(C.c_uint32),
                                         C.c_size_t,C.c_uint64,C.c_uint64,C.c_uint64,C.c_uint64]
        self.lib.fpc1_run_batch.restype=C.c_int
        self.lib.fpc1_check_committed.argtypes=[C.POINTER(IO),C.POINTER(State)]
        self.lib.fpc1_check_committed.restype=C.c_int
        self.io=io
        self.state=State()
        self.arena=arena
        self.assert_owned=assert_owned
        self.keepalive=keepalive
        self.failed=False

    def run_raw(self,plan,input_data,weight_data,*,upload,publish_inputs,acquire_outputs,download,
                timeout_seconds,drain_timeout_seconds=1.0):
        if self.failed or self.state.pending or self.state.blocked:
            raise RuntimeError('An unresolved or failed batch still owns this transport')
        if self.arena!=plan.arena or not plan.tiles or len(plan.tiles)>100000:
            raise ValueError('Plan does not match this arena or command-count limit')
        if len(input_data)!=plan.input_bytes or len(weight_data)!=plan.weight_bytes:
            raise ValueError('Input/weight length differs from plan')
        timeout=int(timeout_seconds*1e9)
        drain_timeout=int(drain_timeout_seconds*1e9)
        if not (0<timeout<1<<63 and 0<drain_timeout<1<<63):
            raise ValueError('Timeouts must be positive and fit signed nanoseconds')
        words=[]
        previous=self.state.last_epoch
        for tile in plan.tiles:
            command=tile.command
            if command.epoch<=previous:
                raise ValueError('Epochs must increase across all batches')
            words.extend(command.words(plan.arena))
            previous=command.epoch
        table=(C.c_uint32*len(words))(*words)
        try:
            self.assert_owned()
            upload(plan.input_base,input_data)
            upload(plan.weight_base,weight_data)
            publish_inputs()
            self.assert_owned()
            rc=self.lib.fpc1_run_batch(C.byref(self.io),C.byref(self.state),table,len(plan.tiles),
                                       *self.arena,timeout,drain_timeout)
            if rc:
                raise NativeFailure(rc,self.state)
            self.assert_owned()
            acquire_outputs()
            output=download(plan.output_base,plan.output_bytes)
            if len(output)!=plan.output_bytes:
                raise RuntimeError('Incomplete output transfer; ownership retained')
            self.assert_owned()
            rc=self.lib.fpc1_check_committed(C.byref(self.io),C.byref(self.state))
            if rc:
                raise NativeFailure(rc,self.state)
            return output,dict(commands=self.state.completed,active_cycles=self.state.active_cycles,
                               input_uploads=1,weight_uploads=1,output_downloads=1)
        except BaseException:
            self.failed=True
            raise
