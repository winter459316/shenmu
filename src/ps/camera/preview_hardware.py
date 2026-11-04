"""Exact remaining preview MMIO map; never probe removed legacy AXI ranges."""
import mmap
from board_dma import TAG

PREVIEW_CORES=(('images',0xA1020000),('filters',0xA1090000),('preview',0xA10A0000),('projection',0xA10C0000))

def check_preview(arena):
    assert not arena.controls,'Close the previous configuration mappings first'
    for name,address in PREVIEW_CORES:
        arena.controls[name]=mmap.mmap(arena.fd,4096,mmap.MAP_SHARED,mmap.PROT_READ|mmap.PROT_WRITE,offset=address)
    for name,offset,identity in (('images',0x20,0x55494632),('filters',0x28,0x50464C31),('preview',0x30,0x50585031),('projection',0x20,0x46475031)):
        value,_=arena.command(name,{offset:0},timeout=2)
        assert value==identity,(name,value)
    value,_=arena.command('images',{0x20:3},timeout=2)
    assert value==TAG,'Image calibration identity changed'
