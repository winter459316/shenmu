"""Refresh only the HDMI status message in this session's two live exports."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
old='    }catch(e){casting=false;note.textContent=e.message;}'
template=(ROOT/'pointcloud_viewer.html').read_text(encoding='utf8')
start=template.index('    }catch(e){\n      casting=false;')
end=template.index('\n    finally{sending=false;}',start)
new=template[start:end]
reports=[]
for job in ('c74ae5e5c0e94fe18b39913c2510f03f','6fc7677660f5402da1aeae97794a12e4'):
    path=ROOT/'live_captures'/job/'viewer.html';before=path.read_bytes();text=before.decode('utf8')
    assert text.count(old)==1
    backup=path.with_name('viewer_before_hdmi_feedback.html');assert not backup.exists();backup.write_bytes(before)
    after=text.replace(old,new).encode('utf8');path.write_bytes(after)
    reports.append({'job_id':job,'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()})
(ROOT/'board_evidence'/'hdmi_feedback_update.json').write_text(json.dumps(reports,indent=2))
print(json.dumps({'updated':len(reports),'services_restarted':False,'geometry_changed':False}))
