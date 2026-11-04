from pathlib import Path
import urllib.request,urllib.parse,re
p=Path(__file__).resolve().parent/'weights/model_best_bp2_serialize.pth'
h=p.read_text(encoding='utf8')
a=re.search('action="([^"]+)"',h).group(1)
d=dict(re.findall('name="([^"]+)" value="([^"]+)"',h))
urllib.request.urlretrieve(a+'?'+urllib.parse.urlencode(d),p)
assert p.stat().st_size==71098210,p.stat().st_size
print('Fast-FoundationStereo official checkpoint:',p.stat().st_size,flush=True)
