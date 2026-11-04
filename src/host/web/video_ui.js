(() => {
  'use strict';
  const el=id=>document.getElementById(id),canvas=el('video-canvas'),ctx=canvas.getContext('2d');
  let recording=false,manifest=null,active=false,playing=false,displayed=-1,wanted=0,loading=false,generation=0;
  let origin=0,offset=0,last=null,pending=false;
  let hdmiLease=null,hdmiPending=null,hdmiSending=false,hdmiSequence=0;
  const images=new Map();
  const clock=t=>{t=Math.max(0,t);return String(Math.floor(t/60)).padStart(2,'0')+':'+String(Math.floor(t%60)).padStart(2,'0')+'.'+String(Math.floor(t%1*10));};
  const note=s=>el('video-status').textContent=s;
  async function api(op,args={}){
    const r=await fetch('/api/video/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify(args)});
    const data=await r.json();if(!r.ok)throw Error(data.error||'视频操作失败');return data;
  }
  function close(){
    const lease=hdmiLease;hdmiLease=null;hdmiPending=null;
    active=false;playing=false;generation++;loading=false;el('video-playback').hidden=true;el('video-controls').hidden=true;
    if(lease)fetch('/api/video/replay-end',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify({owner:lease.owner,generation:lease.generation}),keepalive:true}).catch(()=>{});
  }
  function queueHdmi(){
    if(!hdmiLease||!active)return;
    const rgba=ctx.getImageData(0,0,1280,480).data,bgr=new Uint8Array(1280*480*3);
    for(let i=0,j=0;i<rgba.length;i+=4,j+=3){bgr[j]=rgba[i+2];bgr[j+1]=rgba[i+1];bgr[j+2]=rgba[i];}
    hdmiPending={...hdmiLease,pixels:bgr,sequence:++hdmiSequence};sendHdmi();
  }
  async function sendHdmi(){
    if(hdmiSending||!hdmiPending)return;
    const frame=hdmiPending;hdmiPending=null;hdmiSending=true;
    try{
      const r=await fetch('/api/video/hdmi-frame',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Viewer-Token':window.FAST_UI_TOKEN,'X-Replay-Owner':frame.owner,'X-Replay-Generation':frame.generation,'X-Replay-Sequence':String(frame.sequence)},body:frame.pixels});
      if(!r.ok){const result=await r.json();throw Error(result.error||'HDMI 回放同步失败');}
      canvas.dataset.hdmiSequence=String(frame.sequence);
    }catch(e){if(active&&hdmiLease?.generation===frame.generation)note('HDMI：'+e.message);}
    finally{hdmiSending=false;sendHdmi();}
  }
  window.videoReplay={close,get recording(){return recording;},get active(){return active;}};
  function buttons(){
    const busy=state.busy||state.pending||pending;
    el('video-start').disabled=recording||busy;el('video-stop').disabled=!recording||pending;
    el('video-replay').disabled=recording||busy||!last;
    el('video-start').classList.toggle('recording',recording);
    el('video-play').disabled=playing||!active;el('video-pause').disabled=!playing||!active;
    el('video-reconstruct').disabled=!active||displayed<0||loading||busy||recording;
  }
  function position(t){
    let low=0,high=manifest.timestamps.length;
    while(low<high){const mid=(low+high)>>1;if(manifest.timestamps[mid]<=t)low=mid+1;else high=mid;}
    return Math.max(0,low-1);
  }
  function image(index){
    if(!images.has(index)){
      const im=new Image();im.src='/api/video/frame?id='+manifest.id+'&frame='+index;
      images.set(index,im.decode().then(()=>im));
    }
    for(const key of images.keys())if(Math.abs(key-index)>6)images.delete(key);
    return images.get(index);
  }
  function title(){
    const text='AMD 深目--内窥镜3D感知系统';
    ctx.save();ctx.font='bold 24px "Microsoft YaHei", sans-serif';ctx.textAlign='right';ctx.textBaseline='top';
    const width=ctx.measureText(text).width;ctx.fillStyle='rgba(0,0,0,.65)';ctx.fillRect(canvas.width-width-30,10,width+20,40);
    ctx.fillStyle='#fff';ctx.fillText(text,canvas.width-20,17);ctx.restore();
  }
  async function render(){
    if(loading||!active||displayed===wanted)return;loading=true;buttons();const token=generation,index=wanted;
    try{
      const im=await image(index);if(!active||generation!==token)return;
      if(index===wanted){
        ctx.drawImage(im,0,0,1280,480);title();displayed=index;el('video-seek').value=String(index);
        el('video-time').textContent=clock(manifest.timestamps[index])+' / '+clock(manifest.duration)+' · 第 '+(index+1)+' 帧';
        canvas.dataset.frame=String(index);canvas.dataset.recordingId=manifest.id;
        queueHdmi();
      }
    }catch(e){if(token===generation){playing=false;wanted=displayed;note('回放读取失败：'+e.message);}}
    finally{if(token===generation){loading=false;buttons();if(active&&displayed!==wanted)requestAnimationFrame(render);}}
  }
  function tick(now){
    if(active&&playing){
      const t=(now-origin)/1000+offset;
      wanted=position(Math.min(t,manifest.duration));render();
      if(t>=manifest.duration){playing=false;offset=manifest.timestamps[wanted];buttons();}
    }
    requestAnimationFrame(tick);
  }
  function pause(){
    playing=false;offset=manifest&&displayed>=0?manifest.timestamps[displayed]:0;wanted=Math.max(0,displayed);buttons();
  }
  el('video-start').onclick=async()=>{
    pending=true;buttons();
    try{await api('start');recording=true;setView('live');note('正在录制原始彩色双目画面…');}
    catch(e){note(e.message);}finally{pending=false;buttons();}
  };
  el('video-stop').onclick=async()=>{
    pending=true;buttons();note('正在结束并保存录制…');
    try{const s=await api('stop');recording=s.recording;last=s.last;note(s.error||(last?'已保存 '+last.frames+' 帧 · '+clock(last.duration)+'，可以回放并暂停重建。':'未收到视频帧，请重新录制。'));}
    catch(e){note(e.message);}finally{pending=false;buttons();}
  };
  el('video-replay').onclick=async()=>{
    pending=true;buttons();
    try{
      const r=await fetch('/api/video/manifest?id='+last.id);manifest=await r.json();if(!r.ok)throw Error(manifest.error);
      setView('live');images.clear();generation++;active=true;displayed=-1;wanted=0;offset=0;loading=false;playing=false;
      hdmiSequence=0;
      try{hdmiLease=await api('replay-begin',{owner:crypto.randomUUID().replaceAll('-','')});}
      catch(e){hdmiLease=null;note('本机回放可用；HDMI 暂未连接：'+e.message);}
      el('video-playback').hidden=false;el('video-controls').hidden=false;
      el('video-seek').max=String(manifest.frames-1);el('view-title').textContent='上次录制 · 双目视频回放';el('view-badge').textContent='视频回放';
      await render();playing=true;origin=performance.now();note('回放可暂停或拖动进度；三维重建使用当前显示的原始双目帧。');
    }catch(e){note(e.message);}finally{pending=false;buttons();}
  };
  el('video-play').onclick=()=>{if(!active)return;offset=displayed>=manifest.frames-1?0:manifest.timestamps[Math.max(0,displayed)];origin=performance.now();playing=true;buttons();};
  el('video-pause').onclick=pause;
  el('video-seek').oninput=()=>{playing=false;wanted=Number(el('video-seek').value);offset=manifest.timestamps[wanted];render();buttons();};
  el('video-reconstruct').onclick=async()=>{
    pause();const source={id:manifest.id,frame:displayed};pending=true;buttons();
    try{
      await api('reconstruct',source);state.busy=true;close();setView('live');
      note('正在重建回放第 '+(source.frame+1)+' 帧 · '+clock(manifest.timestamps[source.frame])+'；完成后自动显示三维模型。');
    }catch(e){note(e.message);}finally{pending=false;buttons();}
  };
  async function poll(){
    try{
      const r=await fetch('/api/video/status');if(!r.ok)throw Error('视频服务暂不可用');const s=await r.json();
      const ended=recording&&!s.recording;recording=s.recording;last=s.last;
      if(recording)note('录制中 '+clock(s.elapsed_seconds)+' · '+s.frames+' 帧 · 原始彩色双目');
      else if(ended||s.error)note(s.error||(last?'录制已保存，可以回放。':'本次没有录到视频帧。'));
      el('video-tag').textContent=recording?'● 正在录制':last?clock(last.duration)+' · '+last.frames+' 帧':'原始双目 · 每眼 640×480';
      if(active&&hdmiLease)await api('replay-heartbeat',{owner:hdmiLease.owner,generation:hdmiLease.generation});
    }catch(e){note(e.message);}finally{buttons();setTimeout(poll,700);}
  }
  window.addEventListener('pagehide',close);
  tick(performance.now());poll();
})();
