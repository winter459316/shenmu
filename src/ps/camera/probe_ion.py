"""Allocate a bounded ION CMA buffer, prove every physical page, then free it.
No DMA is started and no FPGA or device registers are touched.
"""
import ctypes,fcntl,json,mmap,os,struct,zlib
ion=os.open('/dev/ion',os.O_RDWR)
query=bytearray(struct.pack('IIQII',0,0,0,0,0))
fcntl.ioctl(ion,0xc0184908,query,True)
count=struct.unpack('IIQII',query)[0]
assert 0<count<32
heaps=ctypes.create_string_buffer(count*52)
query=bytearray(struct.pack('IIQII',count,0,ctypes.addressof(heaps),0,0))
fcntl.ioctl(ion,0xc0184908,query,True)
entries=[]
for i in range(count):
 name,kind,hid,*_=struct.unpack_from('32sIIIII',heaps.raw,i*52)
 entries.append({'name':name.split(b'\0')[0].decode(),'type':kind,'heap_id':hid})
selected=next(h for h in entries if h['type']==4)
size=96*1024*1024
allocation=bytearray(struct.pack('QIIII',size,1<<selected['heap_id'],0,0,0))
fcntl.ioctl(ion,0xc0184900,allocation,True)
fd=struct.unpack('QIIII',allocation)[3]
try:
 with mmap.mmap(fd,size,flags=mmap.MAP_SHARED,prot=mmap.PROT_READ|mmap.PROT_WRITE) as memory:
  address=ctypes.addressof(ctypes.c_char.from_buffer(memory));page=os.sysconf('SC_PAGE_SIZE')
  for offset in range(0,size,page):memory[offset:offset+4]=struct.pack('I',offset^0x51a7c3e9)
  with open('/proc/self/pagemap','rb',buffering=0) as p:
   p.seek(address//page*8);data=p.read(size//page*8)
  pfns=[]
  for entry, in struct.iter_unpack('Q',data):
   assert entry>>63==1,'Page not present: '+hex(entry)+' page_size='+str(page)+' address='+hex(address)+' read_bytes='+str(len(data))
   pfns.append(entry&((1<<55)-1))
  assert pfns[0]!=0 and all(b==a+1 for a,b in zip(pfns,pfns[1:])),'Not physically contiguous'
  assert len(pfns)==size//page
  assert all(struct.unpack_from('I',memory,offset)[0]==offset^0x51a7c3e9 for offset in range(0,size,page))
  result={'heaps':entries,'allocated_bytes':size,'flags':0,'physical_start':hex(pfns[0]*page),'physical_end_exclusive':hex((pfns[-1]+1)*page),'page_bytes':page,'pages_checked':len(pfns),'contiguous':True,'cpu_readback_pass':True,'dma_started':False}
  print(json.dumps(result),flush=True)
finally:
 os.close(fd);os.close(ion)
