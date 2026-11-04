"""Finite injected input-event sequence, with no GPIO or actual HTTP requests."""
from physical_keys import Actions
calls=[]
def fake(path,body=None):
    calls.append((path,body))
    if path=='/stereo/status':return dict(busy=False,section_busy=False,standby=False)
    if path=='/stereo/capture':return dict(accepted=True,job_id='test')
    if path=='/status':return dict(mode='color')
    return {}
a=Actions(fake,held={103})
for event in [(1,103,1),(1,103,2),(1,105,1),(1,106,1),(1,28,1)]:a.event(*event)
assert calls==[]
for event in [(1,103,0),(1,103,1),(1,103,1),(1,103,2),(1,108,1),(1,108,2)]:a.event(*event)
assert calls==[('/standby',{'enabled':False}),('/standby',{'enabled':True})]
b=Actions(fake,pl_enabled=True);calls.clear()
b.event(0,3,0);b.event(1,106,1);assert calls==[]
b.resync({106});b.event(1,106,1);assert calls==[]
for event in [(1,106,0),(1,106,1),(1,106,2),(1,106,1)]:b.event(*event)
assert calls==[('/stereo/status',None),('/stereo/capture',{})]
b.event(1,105,1);assert calls[-1]==('/preview/mode',{'mode':'gray'})
def busy(path,body=None):
    assert path=='/stereo/status' and body is None
    return dict(busy=True,section_busy=False,standby=False)
c=Actions(busy,pl_enabled=True);c.event(1,106,1)
assert c.last['result']=='ignored_while_busy_or_standby'
print('PHYSICAL_KEYS_EVENT_SAFETY_PASS: held/repeat/unsupported/drop/resync/busy',flush=True)
