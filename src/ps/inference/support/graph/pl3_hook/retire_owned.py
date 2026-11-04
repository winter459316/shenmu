"""Revoke mapping exports only after the caller's owned completion/fence proof.

Does not close mappings, unlock, reset, clear faults or modify Native State.
The caller can then close its mappings even while retired transport aliases
are retained by a Python callback frame.
"""


def retire(transport, assert_retirable):
    assert_retirable()
    # Revoke before dropping exports: an accidental later native call receives
    # an invalid IO capability, never a pointer into a closed/reconfigured map.
    for field in ('opaque', 'read32', 'write32', 'barrier', 'now_ns', 'pause'):
        setattr(transport.io, field, None)
    transport.size = 0
    transport.mem_address = 0
    transport.reg_address = 0
    def revoked():
        raise RuntimeError('Owned transport has been retired after its fence')
    transport.assert_owned = revoked
    transport.assert_image_loaded = revoked
    transport.keepalive = ()
    transport.reg_view = None
    transport.mem_view = None
