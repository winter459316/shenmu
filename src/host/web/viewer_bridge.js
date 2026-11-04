/* Computer-side controls for the unchanged viewer and unchanged board results. */
(()=>{
  if(parent===window)return;
  const allowed={mode:['mesh','points','clay'],color:['rgb','depth','solid'],projection:['camera','orthographic'],'texture-mode':['photo','vertex'],shading:['smooth','flat']};
  const numeric={size:[1,8],light:[-180,180]};
  const $=id=>document.getElementById(id);
  const emit=(data,transfer=[])=>parent.postMessage({type:'fast_viewer_state',...data},location.origin,transfer);
  const currentView=()=>$('mode').value==='points'?'points':$('mode').value==='clay'||$('color').value==='solid'?'clay':'surface';
  let lastSelection=-1,lastStats='',lastControls='',lastPose='',hdmiWork=false;
  function snapshot(){
    if(hdmiWork)return;
    const controls={};for(const id of [...Object.keys(allowed),...Object.keys(numeric)]){const el=$(id);if(el)controls[id]={value:el.value,disabled:el.disabled};}
    const pose=JSON.stringify([yaw,pitch,zoom,pan,controls,window.sectionView?.revision||0]);
    if(pose!==lastPose){lastPose=pose;emit({kind:'pose_changed'});}
    const encoded=JSON.stringify(controls),stats=$('stats')?.textContent||'';
    if(encoded!==lastControls||stats!==lastStats){lastControls=encoded;lastStats=stats;emit({kind:'controls',controls,stats});}
    if(typeof selection==='number'&&selection>=0&&selection!==lastSelection){
      lastSelection=selection;emit({kind:'selection',pixel:pixels[selection],xyz_mm:[xyz[3*selection]*1000,xyz[3*selection+1]*1000,xyz[3*selection+2]*1000]});
    }else if(typeof selection==='number'&&selection<0)lastSelection=-1;
  }
  let readySent=false;
  function announceReady(){
    if(readySent||document.body.dataset.renderStatus!=='ready'||(data.texture_image&&!textureReady))return;
    readySent=true;emit({kind:'ready'});snapshot();
    requestAnimationFrame(()=>requestAnimationFrame(()=>emit({kind:'timing_first_frame',job_id:location.pathname.split('/')[2]})));
  }
  window.addEventListener('stereo-rendered',()=>{snapshot();announceReady();});
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==parent||event.data?.type!=='fast_viewer_control')return;
    const m=event.data;
    if(m.action==='hello'){if(readySent){emit({kind:'ready'});snapshot();}else announceReady();return;}
    if(m.control){
      const el=$(m.control);if(!el)return;
      if(allowed[m.control]){if(!allowed[m.control].includes(m.value))return;}
      else if(numeric[m.control]){const n=Number(m.value),range=numeric[m.control];if(!Number.isFinite(n)||n<range[0]||n>range[1])return;}
      else return;
      el.value=m.value;el.dispatchEvent(new Event('input'));snapshot();
    }else if(['front','oblique','reset'].includes(m.action)){$(m.action).click();snapshot();}
    else if(m.action==='redraw'){if(typeof render==='function')render();snapshot();}
    else if(['hdmi_bundle','hdmi_settled','hdmi_live'].includes(m.action)){
      const saved={yaw,pitch,zoom,pan:pan.slice(),selection,view:currentView(),values:{}};
      for(const id of ['mode','color','projection','texture-mode','size','shading'])saved.values[id]=$(id).value;
      hdmiWork=true;
      try{
        if(m.action==='hdmi_live'){
          const view=saved.view;
          // Interactive frames use one quarter of the pixels; settled frames
          // retain full resolution and the user's exact material settings.
          const shot=window.stereoCaptureHdmi(640,360),buffer=shot.bgr.slice().buffer;
          emit({kind:'hdmi_live',request_id:m.request_id,job_id:m.job_id,generation:m.generation,view,buffer,capture_ms:shot.captureMs},[buffer]);
        }else{
          const started=performance.now(),frames={};
          for(const [mode,view,title] of [['points','points','三维点云  /  POINT CLOUD'],['mesh','surface','彩色表面  /  TEXTURED SURFACE'],['clay','clay','灰色表面  /  GRAY SURFACE']]){
            const preserve=m.action==='hdmi_settled'&&view===saved.view;
            if(preserve){for(const [id,value] of Object.entries(saved.values))$(id).value=value;}
            else{$('mode').value=mode;$('color').value=mode==='clay'?'solid':'rgb';$('texture-mode').value='photo';$('shading').value='smooth';}
            $('mode').dispatchEvent(new Event('input'));
            const shot=window.stereoCaptureHdmi(1280,720),ctx=shot.canvas.getContext('2d');
            ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#0b1020';ctx.fillRect(0,0,1280,58);ctx.fillRect(0,670,1280,50);
            const heading=preserve&&saved.values.color==='depth'?title.replace('彩色表面  /  TEXTURED SURFACE','深度着色表面  /  DEPTH SURFACE'):title;
            ctx.fillStyle='#e5edf8';ctx.font='22px Microsoft YaHei,sans-serif';ctx.fillText(heading,24,37);
            ctx.font='19px Microsoft YaHei,sans-serif';ctx.fillText('PS_KEY1 切换结果    PL_KEY1 返回预览',24,702);
            frames[view]=shot.canvas.toDataURL('image/png');
          }
          emit({kind:m.action,request_id:m.request_id,job_id:m.job_id,generation:m.generation,frames,capture_ms:performance.now()-started});
        }
      }catch(error){emit({kind:'hdmi_error',request_id:m.request_id,job_id:m.job_id,generation:m.generation,error:error.message});}
      finally{
        for(const [id,value] of Object.entries(saved.values))$(id).value=value;
        $('mode').dispatchEvent(new Event('input'));yaw=saved.yaw;pitch=saved.pitch;zoom=saved.zoom;pan=saved.pan;selection=saved.selection;
        render();hdmiWork=false;snapshot();
      }
    }
    else if(m.action==='save_png'){
      if(typeof render==='function')render();const canvas=$('canvas');if(canvas.width&&canvas.height)emit({kind:'png',data:canvas.toDataURL('image/png')});
    }else if(Number.isInteger(m.pixel)&&m.pixel>=0&&typeof originalXYZ!=='undefined'&&m.pixel<originalXYZ.length/3){
      emit({kind:'selection',pixel:m.pixel,xyz_mm:[originalXYZ[3*m.pixel]*1000,originalXYZ[3*m.pixel+1]*1000,originalXYZ[3*m.pixel+2]*1000]});
    }
  });
  announceReady();
})();
