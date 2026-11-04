import json
from pathlib import Path
from board_dma import Arena,TAG
a=Arena(True);results={}
try:
    for core,identity in (('sgm',0x55534738),('images',0x55494632),('geometry',0x55474532),('completion',0x43475032)):
        # All HLS cores have command at 0x20 and return at 0x10.
        value,seconds=a.command(core,{0x20:0},timeout=2)
        assert value==identity,(core,hex(value));results[core]={'identity':hex(value),'seconds':seconds}
        if core in ('images','geometry'):
            value,_=a.command(core,{0x20:3},timeout=2);assert value==TAG
            results[core]['calibration_tag']=hex(value)
    results['dma_reservation']=a.reservation
    Path(__file__).with_name('core_identities_verified.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
finally:a.close()
