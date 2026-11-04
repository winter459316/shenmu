/* Render the four HDMI views on the PC; no disparity/geometry changes. */
(()=>{
  let building=null,lastStatus=null,dirty=false,settle=false,lastPose=0;
  let capturing=null,pendingLive=null,sendingLive=null,pumpTimer=null,nextCapture=0;
  const framePeriod=1000/30;
  const liveStats={captured:0,sent:0,replaced:0,failed:0,capture_ms:0,roundtrip_ms:0};
  function reportLive(){document.body.dataset.hdmiLiveStats=JSON.stringify(liveStats);}
  function wakePump(delay=0){if(pumpTimer!==null)clearTimeout(pumpTimer);pumpTimer=setTimeout(()=>{pumpTimer=null;pump();},delay);}
  function clearLive(){if(sendingLive)sendingLive.abort.abort();capturing=null;pendingLive=null;sendingLive=null;if(pumpTimer!==null)clearTimeout(pumpTimer);pumpTimer=null;}
  let attempts=0,retryAfter=0,attemptGeneration=null;
  function cancelBuild(){if(building)building.abort.abort();building=null;clearLive();dirty=false;settle=false;}
  function newRequest(fields){return {...fields,request_id:crypto.randomUUID(),abort:new AbortController(),started:performance.now()};}
  function dispatch(request){const {abort,...message}=request;send({action:request.kind,...message});}
  const note=document.getElementById('hdmi-note');
  const titles={preview:'实时预览',processing:'Fast 处理中',waiting:'正在准备结果',pair:'视差 / 深度并排',points:'三维点云',surface:'彩色表面',clay:'灰色表面'};
  function pngBytes(url){const raw=atob(url.split(',')[1]),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);return bytes;}
  async function postFrame(view,data,request,live=false,activate=false){
    const headers={'Content-Type':live?'application/octet-stream':'image/png','X-Viewer-Token':window.FAST_UI_TOKEN,'X-Photo-Id':request.job_id,'X-Fast-Generation':request.generation,'X-Fast-View':view};
    if(request.epoch!==undefined){headers['X-HDMI-Epoch']=String(request.epoch);headers['X-HDMI-Activate']=activate?'1':'0';}
    const response=await fetch('/api/hdmi/frame',{method:'POST',headers,body:live?data:pngBytes(data),signal:request.abort.signal});
    const result=await response.json();if(!response.ok)throw Error(result.error||'HDMI 帧传输失败');
    if(request.epoch!==undefined){request.epoch=result.display_epoch;if(lastStatus&&lastStatus.generation===request.generation&&lastStatus.display_epoch<=result.display_epoch){lastStatus.display_epoch=result.display_epoch;lastStatus.view=result.active_view;}}
  }
  function image(url){return new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve(im);im.onerror=()=>reject(Error('色彩图载入失败'));im.src=url;});}
  async function pairFrame(){
    const maps=state.colorMaps,canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;
    const c=canvas.getContext('2d');c.fillStyle='#0b1020';c.fillRect(0,0,1280,720);
    c.fillStyle='#e5edf8';c.font='24px Microsoft YaHei,sans-serif';c.fillText('视差图  /  DISPARITY',45,42);c.fillText('深度图  /  DEPTH',685,42);
    const images=await Promise.all([image(maps.disparity.url),image(maps.depth.url)]);
    c.imageSmoothingEnabled=false;c.drawImage(images[0],80,78,480,540);c.drawImage(images[1],720,78,480,540);
    for(let side=0;side<2;side++){
      const x=45+side*640,gradient=c.createLinearGradient(x,0,x+550,0);
      mapPalette.forEach((rgb,i)=>gradient.addColorStop(i/(mapPalette.length-1),'rgb('+rgb.join(',')+')'));
      c.fillStyle=gradient;c.fillRect(x,635,550,10);c.fillStyle='#dceafa';c.font='18px Microsoft YaHei,sans-serif';
      const range=side?maps.depth.range:maps.disparity.range,unit=side?' cm':' px',scale=side?10:1;
      if(range){const near=side?range[0]:range[1],far=side?range[1]:range[0];c.fillText('近 '+(near/scale).toFixed(1)+unit,x,668);c.textAlign='right';c.fillText('远 '+(far/scale).toFixed(1)+unit,x+550,668);c.textAlign='left';}
    }
    c.font='18px Microsoft YaHei,sans-serif';c.fillText('PS_KEY1 切换结果    PL_KEY1 返回预览    PL_KEY2 再拍一张    黑色 = 无效匹配',28,704);
    return canvas.toDataURL('image/png');
  }
  window.updateFastHdmi=hdmi=>{
    if(!hdmi)return;
    if(lastStatus&&lastStatus.generation===hdmi.generation&&lastStatus.display_epoch>hdmi.display_epoch)return;
    if(lastStatus&&(hdmi.generation!==lastStatus.generation||hdmi.display_epoch!==lastStatus.display_epoch||hdmi.job_id!==lastStatus.job_id)){clearLive();dirty=false;settle=false;}
    lastStatus=hdmi;
    if(window.videoReplay?.active){cancelBuild();note.textContent='HDMI：视频回放 · 与电脑同步';return;}
    if(state.busy){clearLive();dirty=false;settle=false;}
    if(attemptGeneration!==hdmi.generation){attemptGeneration=hdmi.generation;attempts=0;retryAfter=0;}
    if(building&&(state.busy||building.job_id!==state.current||building.generation!==hdmi.generation||performance.now()-building.started>8000)){
      const timedOut=!state.busy&&building.job_id===state.current&&building.generation===hdmi.generation;
      cancelBuild();if(timedOut)retryAfter=performance.now()+1000;
    }
    const photoTitle=hdmi.view?.startsWith('photo_')?'所拍照片 · '+filterNames[hdmi.view.slice(6)]:null;
    const liveTitle=hdmi.view==='preview'?'实时预览 · '+(filterNames[hdmi.preview_mode]||'原始彩色'):null;
    note.textContent=hdmi.pc_online===false&&hdmi.error?'HDMI：板卡未连接，已保存结果仍可查看':hdmi.error?'HDMI：'+hdmi.error:'HDMI：'+(photoTitle||liveTitle||titles[hdmi.view]||'连接中')+(hdmi.waiting_for_render?' · 电脑正在生成画面':'');
    if(attempts>=3&&hdmi.waiting_for_render){note.textContent='HDMI：画面生成未完成，可刷新网页重试；仍可按 PL_KEY2 拍下一张';return;}
    if(!hdmi.waiting_for_render||state.busy||!state.colorMaps||!state.frameReady||state.current!==hdmi.job_id||building||performance.now()<retryAfter)return;
    clearLive();
    attempts++;building=newRequest({job_id:hdmi.job_id,generation:hdmi.generation,kind:'hdmi_bundle'});
    window.photoTiming.mark('hdmi_prepare_started',state.current);
    dispatch(building);
  };
  window.wakeFastHdmi=()=>{if(lastStatus)window.updateFastHdmi(lastStatus);};
  function liveReady(){return !window.videoReplay?.active&&!building&&!state.busy&&state.view==='model'&&state.frameReady&&lastStatus&&!lastStatus.waiting_for_render&&lastStatus.job_id===state.current&&['points','surface','clay'].includes(lastStatus.view);}
  function current(request){return liveReady()&&request.job_id===state.current&&request.generation===lastStatus.generation&&request.epoch===lastStatus.display_epoch;}
  async function sendLatest(){
    if(sendingLive||!pendingLive)return;
    const request=pendingLive;pendingLive=null;
    if(!current(request)){dirty=true;wakePump();return;}
    sendingLive=request;const started=performance.now();
    try{
      await postFrame(request.view,request.buffer,request,true,true);
      liveStats.sent++;liveStats.roundtrip_ms=performance.now()-started;
    }catch(error){
      liveStats.failed++;
      // A rejected epoch must never be rebased onto a newer physical selection.
      if(sendingLive===request){pendingLive=null;dirty=false;settle=false;}
    }finally{
      if(sendingLive===request)sendingLive=null;
      reportLive();sendLatest();wakePump();
    }
  }
  function pump(){
    if(!liveReady())return;
    const now=performance.now();
    if(dirty&&!capturing){
      if(now<nextCapture){wakePump(nextCapture-now);return;}
      dirty=false;settle=true;
      if(now-nextCapture>framePeriod)nextCapture=now;
      nextCapture+=framePeriod;
      capturing=newRequest({job_id:state.current,generation:lastStatus.generation,epoch:lastStatus.display_epoch,kind:'hdmi_live'});
      dispatch(capturing);return;
    }
    if(settle&&!dirty&&!capturing&&!pendingLive&&!sendingLive){
      if(now-lastPose<350){wakePump(350-(now-lastPose));return;}
      settle=false;
      building=newRequest({job_id:state.current,generation:lastStatus.generation,epoch:lastStatus.display_epoch,kind:'hdmi_settled'});
      dispatch(building);
    }
  }
  // Capture and upload overlap; one upload and only the latest unsent frame.
  // Status polling also recovers a renderer that failed to answer.
  setInterval(()=>{
    const now=performance.now();
    if(capturing&&now-capturing.started>8000){capturing=null;dirty=true;}
    if(sendingLive&&now-sendingLive.started>8000)sendingLive.abort.abort();
    pump();
  },250);
  window.addEventListener('message',async event=>{
    if(event.origin!==location.origin||event.source!==document.getElementById('viewer').contentWindow||event.data?.type!=='fast_viewer_state')return;
    const m=event.data;
    if(m.kind==='pose_changed'){dirty=true;lastPose=performance.now();wakePump();return;}
    if(capturing&&m.request_id===capturing.request_id&&m.generation===capturing.generation&&m.job_id===capturing.job_id&&['hdmi_live','hdmi_error'].includes(m.kind)){
      const request=capturing;capturing=null;
      if(m.kind==='hdmi_live'&&current(request)){
        liveStats.captured++;liveStats.capture_ms=m.capture_ms;
        if(pendingLive)liveStats.replaced++;
        pendingLive={...request,view:m.view,buffer:m.buffer};sendLatest();
      }
      reportLive();wakePump();return;
    }
    const request=building;
    if(!request||m.request_id!==request.request_id||m.generation!==request.generation||m.job_id!==request.job_id||!['hdmi_bundle','hdmi_settled','hdmi_live','hdmi_error'].includes(m.kind))return;
    try{
      if(m.kind==='hdmi_error')throw Error(m.error);
      if(state.current!==request.job_id||state.busy)throw Error('照片已切换');
      if(m.kind==='hdmi_live')await postFrame(m.view,m.buffer,request,true,true);
      else{
        if(m.kind==='hdmi_bundle')await postFrame('pair',await pairFrame(),request);
        for(const view of ['points','surface','clay'])await postFrame(view,m.frames[view],request);
        if(m.kind==='hdmi_bundle'){
          window.photoTiming.mark('hdmi_frames_uploaded',request.job_id);
          const reply=await fetch('/api/hdmi/publish',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify({job_id:request.job_id,generation:request.generation,render_ms:m.capture_ms,prepare_ms:performance.now()-request.started}),signal:request.abort.signal});
          const result=await reply.json();if(!reply.ok)throw Error(result.error||'HDMI 发布失败');
          note.textContent='HDMI：视差 / 深度并排 · PS_KEY1 切换点云、彩色/灰色表面';attempts=0;
        }
      }
    }catch(error){
      console.warn('HDMI attempt failed',request.job_id,request.request_id,request.kind,String(error));
      if(building===request&&request.kind==='hdmi_bundle'){retryAfter=performance.now()+1000;note.textContent='HDMI：'+error.message+'；正在重试';}
      // A physical key or new photo invalidates in-flight frames; never switch it back.
    }finally{if(building===request)building=null;wakePump();}
  });
})();
