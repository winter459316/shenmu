"""One bounded PL3 interval between original PL2 calls, for saved-photo proof.

The caller holds capture/configuration leases and a verified frozen preview.
This validation controller has no active HDMI helper. Every old PL2 mapping
must have been released before entry. Unknown DMA retains the entire context
and never returns through ORT into an unsafe original-image cleanup path.
"""
from pathlib import Path
import ctypes as C
import hashlib
import json
import mmap
import os
import re
import signal
import struct
import time
import traceback
import numpy as np
from board_dma import Arena
import pause_preview_board as preview
import test_hardware_board as h
from native_runtime_20261027 import State
from owned_memory_20261027 import OwnedMemory
from mmio_read44_20261027 import read_register
from fault_observer44_20261027 import diagnostics, fenced_failure
from bind_spin_20261028 import SpinPause
from copyout4_20261028 import CopyOut4
from retire_owned_20261028 import retire

F = C.POINTER(C.c_float)
I = C.POINTER(C.c_int64)
Callback = C.CFUNCTYPE(C.c_int, C.c_uint32, F, F, F, F, I, I, I)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PhysicalBridge:
    def __init__(self, library, root, manifest, assert_outer_owned, job):
        self.root = Path(root)
        self.R = self.root.parent/'fast_infer2'
        self.S = self.root.parent/'usb320_hdmifps'
        assert re.fullmatch('[0-9a-f]{32}',job)
        self.evidence_root=self.R/'jobs'/job
        assert self.evidence_root.is_dir()
        self.spec = manifest['physical_bridge']
        assert self.spec['scratch_lifetime_reviewed']
        self.qualified = self.spec['physical']
        self.assert_outer_owned = assert_outer_owned
        self.saved = None
        self.ctx = None
        self.records, self.errors, self.failed_native_states = [], [], []
        self.interval = {}
        self.rows = {r['index']: r for r in self.spec['records']}
        self.expected = {r['index']: r for r in self.spec.get('hook_reference',[])}
        self.bit = self.root/self.spec['bit_file']
        assert sha(self.bit.read_bytes()) == self.qualified['sha256']
        self.bit_stat = self.bit.stat()
        assert self.qualified['physical_qualified'] and self.qualified['physical_mmcm_verified']
        assert self.qualified['compute_read_acceptance'] == 16
        self.copier = CopyOut4(self.root/'fpc1_copyout4_20261028.so')
        self.native = C.CDLL(str(self.root/'fpc1_device_20261027.so'))
        self.native.fpc1_patch_and_validate.argtypes = [C.POINTER(C.c_uint32), C.c_size_t,
                                                       C.c_uint64, C.c_uint64, C.c_uint64]
        self.native.fpc1_patch_and_validate.restype = C.c_int
        self.native.fpc1_run_batch.argtypes = [C.c_void_p, C.POINTER(State), C.POINTER(C.c_uint32),
            C.c_size_t, C.c_uint64, C.c_uint64, C.c_uint64, C.c_uint64]
        self.native.fpc1_run_batch.restype = C.c_int
        self.native.fpc1_check_committed.argtypes = [C.c_void_p, C.POINTER(State)]
        self.native.fpc1_check_committed.restype = C.c_int
        self.tables = {}
        for index, row in self.rows.items():
            data = (self.root/row['table_file']).read_bytes()
            assert sha(data) == row['table_sha256'] and len(data) == row['commands']*148
            self.tables[index] = (C.c_uint32*(len(data)//4)).from_buffer_copy(data)
        self.library = C.CDLL(str(library))
        self.library.fastpl3_set_callback.argtypes = [Callback]
        self.library.fastpl3_set_callback.restype = None
        self.library.fastpl3_calls.argtypes = []
        self.library.fastpl3_calls.restype = C.c_uint64
        self.callback = Callback(self.compute)
        self.library.fastpl3_set_callback(self.callback)

    def arm(self, saved):
        assert self.saved is None and self.ctx is None and not self.records
        self.saved = saved
        preview.assert_frozen_lease(saved)
        self.owned()

    def owned(self):
        self.assert_outer_owned()
        assert self.saved is not None
        assert self.saved['pause_lease']['frozen']
        assert preview.process_state(self.saved['owners']['full_camera.py']) in ('T','t')

    def image_loaded(self):
        c = self.ctx
        assert c and c['image'] == 'pl3'
        assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip() == 'operating'
        state = json.loads((self.R/'configuration_state.json').read_text())
        assert state['experiment_sha256'] == self.qualified['sha256']
        now = self.bit.stat()
        assert (now.st_ino, now.st_size, now.st_mtime_ns) == \
               (self.bit_stat.st_ino, self.bit_stat.st_size, self.bit_stat.st_mtime_ns)

    def check_original(self, arena):
        for name, address in [('images',0xA1020000), ('fast',0xA1070000), ('mixed',0xA1080000)]:
            arena.controls[name] = mmap.mmap(arena.fd,4096,mmap.MAP_SHARED,
                mmap.PROT_READ|mmap.PROT_WRITE,offset=address)
        assert all(arena.read(name,0)&4 for name in arena.controls), 'Original PL2 master not idle'
        with mmap.mmap(arena.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ,offset=0xA1050000) as video:
            assert struct.unpack_from('<I',video,4)[0]&1, 'This validator requires halted HDMI DMA'
        for name, command, expected in [('images',{0x20:0},0x55494632),
                                       ('fast',{0x20:0},0x46445032),
                                       ('mixed',{0x28:0},0x4d503136)]:
            identity, _ = arena.command(name,command,timeout=2)
            assert identity == expected
        for view in arena.controls.values():
            view.close()
        arena.controls = {}

    def begin(self):
        self.owned()
        preview.assert_frozen_lease(self.saved)
        assert self.ctx is None
        original = json.loads((self.R/'hardware_verified.json').read_text())
        assert json.loads((self.R/'loaded.json').read_text())['sha256'] == original['sha256']
        assert json.loads((self.R/'configuration_state.json').read_text())['new']
        for p in [self.R/'dma.fault', self.S/'dma.fault', self.R.parent/'fast_pl/dma.fault']:
            assert not p.exists(), str(p)
        c = dict(arena=Arena(False), registers=None, view=None, transport=None, backup=None,
                 state=State(), started=False, image='pl2', phase='original_idle',
                 old_idle_verified=False, failed_fence_verified=False,
                 old_configuration=(self.R/'configuration_state.json').read_bytes(),
                 old_loaded=(self.R/'loaded.json').read_bytes())
        self.ctx = c
        self.check_original(c['arena'])
        c['old_idle_verified'] = True
        self.saved['pl3_transfer']=dict(phase='program_pl3',candidate_sha256=self.qualified['sha256'],base=self.spec['memory_base'],bytes=self.spec['memory_bytes'],dead_scratch_contents_not_preserved=True)
        preview.journal(self.saved)
        c['phase'] = 'program_pl3'
        start = time.monotonic()
        (self.R/'loaded.json').write_text(json.dumps(dict(state='switching', active_project='pl3_validation')))
        c['image'] = 'no_dma_started'
        h.program(self.root,self.bit.name)
        c['image'] = 'pl3'
        (self.R/'configuration_state.json').write_text(json.dumps(dict(new=True,experiment_sha256=self.qualified['sha256'])))
        (self.R/'loaded.json').write_text(json.dumps(dict(state='operating',sha256=self.qualified['sha256'],active_project='pl3_validation')))
        self.interval['load_pl3_seconds'] = time.monotonic()-start
        base, size = self.spec['memory_base'], self.spec['memory_bytes']
        assert base == 0x60000000 and base+size <= 0x67000000
        c['registers'] = mmap.mmap(c['arena'].fd,4096,mmap.MAP_SHARED,
            mmap.PROT_READ|mmap.PROT_WRITE,offset=0xa10d0000)
        c['view'] = memoryview(c['arena'].memory)[:size]
        c['transport'] = OwnedMemory(self.root/'fpc1_device_20261027.so',c['registers'],c['view'],base,
            assert_owned=self.owned,assert_image_loaded=self.image_loaded)
        io = c['transport'].io
        assert read_register(io,0) == 0x31435046 and read_register(io,0x28) == 0x44424731
        assert read_register(io,4)&0x13 == 0x11 and read_register(io,8) == 0
        c['phase'] = 'backup_shared_arena'
        start = time.monotonic()
        c['backup'] = None
        self.interval['backup_seconds'] = 0.0
        self.interval['dead_scratch_contents_not_preserved'] = True
        c['phase'] = 'ready'

    def restore_pl2(self):
        self.owned()
        preview.assert_frozen_lease(self.saved)
        c = self.ctx
        assert c is not None
        assert c['old_idle_verified'], 'Never reconfigure an unverified original DMA owner'
        def retirable():
            self.owned()
            if c['started'] and not c['failed_fence_verified']:
                assert c['transport'] is not None
                assert self.native.fpc1_check_committed(C.byref(c['transport'].io),C.byref(c['state'])) == 0
        retirable()
        start = time.monotonic()
        # Callers must establish success/failed-drained safety before entry.
        if c['backup'] is not None:
            assert c['image'] == 'pl3'
            transport = c['transport']
            transport.upload(self.spec['memory_base'],c['backup'])
            assert self.copier.download(transport,self.spec['memory_base'],self.spec['memory_bytes']) == c['backup']
        if c['transport'] is not None:
            retire(c['transport'],retirable)
        c['transport'] = None
        if c['registers'] is not None:
            c['registers'].close()
            c['registers'] = None
        if c['view'] is not None:
            c['view'].release()
            c['view'] = None
        c['phase'] = 'restore_original_image'
        c['image'] = 'drained_before_reconfiguration'
        (self.R/'loaded.json').write_text(json.dumps(dict(state='switching',active_project='pl3_validation')))
        h.program(self.R,'fast_pl.bit.bin')
        c['image'] = 'pl2'
        self.check_original(c['arena'])
        c['arena'].close()
        (self.R/'configuration_state.json').write_bytes(c['old_configuration'])
        (self.R/'loaded.json').write_bytes(c['old_loaded'])
        self.interval['restore_pl2_with_byte_verification_seconds'] = time.monotonic()-start
        self.interval['preserved_native_last_epoch'] = int(c['state'].last_epoch)
        self.saved['pl3_transfer']['phase']='original_pl2_restored'
        preview.journal(self.saved)
        self.ctx = None

    def guard(self,error):
        c = self.ctx
        state = c['state'] if c else State()
        value = dict(passed=False,requires_recovery=True,guardian_pid=os.getpid(),
            phase=c['phase'] if c else 'outside_interval',error=str(error),snapshot=str(h.SNAP),
            pending=int(state.pending),blocked=int(state.blocked),fault=int(state.fault),
            candidate_sha256=self.qualified['sha256'])
        (self.evidence_root/'pl3_guardian.json').write_text(json.dumps(value,indent=2))
        signal.alarm(0)  # A worker watchdog may not tear down unknown DMA.
        (self.R/'pl3_usable_v1.dma.fault').write_text(json.dumps(value))
        (self.R/'dma.fault').write_text(json.dumps(value))
        (self.S/'dma.fault').write_text('PL3 full replay retained its original lease/mappings; inspect before reconfiguration')
        print('PL3_FULL_GUARDIAN_RETAINS_LEASES',flush=True)
        while True:
            time.sleep(1)

    def recover_or_guard(self,error):
        c = self.ctx
        if c is None:
            return
        try:
            if not c['old_idle_verified']:
                self.guard(error)
            if c['started']:
                assert c['image'] == 'pl3' and c['transport'] is not None
                transport, state = c['transport'], c['state']
                if state.pending or state.blocked or state.fault:
                    observed = diagnostics(transport.io,transport.check)
                    fence = fenced_failure(transport.io,transport.check)
                    self.failed_native_states.append(dict(pending=int(state.pending),blocked=int(state.blocked),
                        fault=int(state.fault),status=int(state.status),native_state_hex=C.string_at(C.addressof(state),C.sizeof(state)).hex(),diagnostics=observed,physical_fence=fence))
                    evidence=self.evidence_root/'pl3_failed_native.json'
                    evidence.write_text(json.dumps(dict(failed_native_states=self.failed_native_states,failed_command_not_published=True),indent=2))
                    if not fence:
                        self.guard(error)
                    c['failed_fence_verified'] = True
                else:
                    assert self.native.fpc1_check_committed(C.byref(transport.io),C.byref(state)) == 0
            self.restore_pl2()
        except BaseException as recovery_error:
            self.guard(recovery_error)

    def compute(self,index,xp,wp,bp,yp,xs,ws,ys):
        try:
            assert len(self.records)<3 and index == (827,830,831)[len(self.records)]
            assert tuple(xs[i] for i in range(5)) == tuple(ys[i] for i in range(5)) == (1,56,24,48,40)
            row = self.rows[index]
            expected = self.expected.get(index)
            x = np.ctypeslib.as_array(xp,shape=(2580480,))
            w = np.ctypeslib.as_array(wp,shape=(row['weight_bytes']//4,))
            b = np.ctypeslib.as_array(bp,shape=(56,))
            xdata,wdata = x.tobytes(),w.tobytes()
            if expected is not None:assert sha(xdata)==expected['input_sha256']
            assert wdata == (self.root/('production_%d_weight.bin'%index)).read_bytes()
            assert b.tobytes() == (self.root/('production_%d_bias.bin'%index)).read_bytes()
            if index == 827:
                self.begin()
            c = self.ctx
            assert c and c['image'] == 'pl3'
            transport, state = c['transport'], c['state']
            table = self.tables[index]
            base,size = self.spec['memory_base'],self.spec['memory_bytes']
            timings = {}
            start = time.monotonic()
            epoch = max(int(state.last_epoch)+1,0x2026102844000001)
            assert self.native.fpc1_patch_and_validate(table,row['commands'],base,base+size,epoch) == 0
            transport.upload(row['input_base'],xdata)
            transport.upload(row['weight_base'],wdata)
            transport.barrier()
            timings['upload_and_descriptors'] = time.monotonic()-start
            c['phase'] = 'node_%d_native_batch'%index
            c['started'] = True
            binding = SpinPause(transport.io,self.root/'fpc1_spin_20261028.so')
            start = time.monotonic()
            try:
                rc = self.native.fpc1_run_batch(C.byref(transport.io),C.byref(state),table,row['commands'],base,base+size,
                                              2_000_000_000,1_000_000_000)
            finally:
                binding.restore_callback()
            if rc:
                raise RuntimeError('Physical full-graph node%d native batch returned%d'%(index,rc))
            assert self.native.fpc1_check_committed(C.byref(transport.io),C.byref(state)) == 0
            timings['dispatch_and_compute'] = time.monotonic()-start
            start = time.monotonic()
            raw = self.copier.download(transport,row['output_base'],row['output_bytes'])
            timings['download'] = time.monotonic()-start
            start = time.monotonic()
            # The original full graph retains Relu/LeakyRelu/Mul. Return Conv+bias only.
            result = np.add(np.frombuffer(raw,dtype='<f4').reshape(1,56,24,48,40),b.reshape(1,56,1,1,1),dtype=np.float32)
            if expected is not None:assert sha(result.tobytes())==expected['output_sha256']
            np.copyto(np.ctypeslib.as_array(yp,shape=(x.size,)),result.reshape(-1))
            timings['bias_and_exact_trace_check'] = time.monotonic()-start
            self.records.append(dict(index=index,input_sha256=sha(xdata),output_sha256=sha(result.tobytes()),
                exact_independent_photo_trace=expected is not None,commands=int(state.completed),active_cycles=int(state.active_cycles),seconds=timings))
            c['phase'] = 'node_%d_committed'%index
            if index == 831:
                self.restore_pl2()
            return 0
        except BaseException as error:
            self.errors.append(repr(error))
            traceback.print_exc()
            self.recover_or_guard(error)
            return 1

    def active(self):
        return self.ctx is not None

    def close(self):
        assert self.ctx is None, 'Never detach a callback from an owned PL3 interval'
        self.library.fastpl3_set_callback(Callback())
