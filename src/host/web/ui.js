'use strict';
const $=id=>document.getElementById(id);
const state={current:null,result:null,depth:null,colorMaps:null,busy:false,view:'live',pending:false,frameReady:false,pixel:null,photoMode:'color',displaySelection:null};
const filterNames={color:'原始彩色',auto_enhanced:'自动曝光',gray:'灰度',sobel:'Sobel 边缘',vessel:'血管增强'};
const views={
  live:{title:'左右相机预览',tag:'实时画面',kicker:'CAMERA',short:'预览',guide:'滚轮缩放 · 放大后拖动查看 · 双击恢复 1×'},
  photo:{title:'所拍照片',tag:'同一张静态照片',kicker:'PHOTO',short:'照片滤镜',guide:'原图与滤镜来自同一张照片，不重新拍摄'},
  rectified:{title:'校正后的左右画面',tag:'最近照片',kicker:'RECTIFIED',short:'校正双目',file:'rectified.png',guide:'左右画面使用同一套标定参数进行校正'},
  left:{title:'校正左图',tag:'最近照片',kicker:'REFERENCE',short:'校正左图',file:'reference.png',guide:'单击画面，在右侧读取对应像素的深度'},
  disparity:{title:'Fast 原始视差图',tag:'未经补洞',kicker:'DISPARITY',short:'视差图',file:'disparity.png',guide:'单击画面查询视差与深度 · 黑色为无效点'},
  depth:{title:'深度图',tag:'自适应色阶',kicker:'DEPTH',short:'深度图',file:'depth.png',guide:'单击画面查询光轴深度 Z · 黑色为无效点'},
  model:{title:'三维点云与表面',tag:'电脑渲染',kicker:'3D VIEW',short:'三维模型',guide:'左键旋转 · 右键平移 · 滚轮缩放 · 单击查询深度'}
};
const labels={idle:'准备拍照',starting:'准备处理',capture:'冻结新的左右画面',pause_preview:'准备所拍静态照片',live_preview_start:'显示所拍静态照片',load_pl:'准备计算',rectification:'校正左右画面',fast_inference:'估计视差',geometry:'生成三维坐标',restore_preview:'恢复相机预览',export_3d:'准备三维显示',ready:'处理完成',failed:'处理失败'};
const controls=[...document.querySelectorAll('[data-control]')];
const root='/captures/';
function path(file){return root+state.current+'/'+file;}
function send(message){if(state.frameReady)$('viewer').contentWindow.postMessage({type:'fast_viewer_control',...message},location.origin);}
function syncControls(){for(const el of controls)send({control:el.dataset.control,value:el.value});send({action:'redraw'});}

// Display only: preserve the saved depth/disparity arrays and validity mask.
const mapPalette=[[238,58,42],[255,145,31],[250,224,55],[71,206,105],[22,193,216],[49,83,222]];
function displayRange(values,minSpan){
  if(!values.length)return null;
  values.sort((a,b)=>a-b);
  const quantile=p=>{const i=(values.length-1)*p,l=Math.floor(i);return values[l]+(values[Math.ceil(i)]-values[l])*(i-l);};
  let low=quantile(.02),high=quantile(.98);
  // Avoid making sub-centimetre noise look like a large depth step on flat scenes.
  if(high-low<minSpan){const middle=(low+high)/2;low=Math.max(0,middle-minSpan/2);high=low+minSpan;}
  return [low,high];
}
function colorizeMap(values,range,reverse){
  const d=state.depth,canvas=document.createElement('canvas');canvas.width=d.width;canvas.height=d.height;
  const ctx=canvas.getContext('2d'),image=ctx.createImageData(d.width,d.height),rgba=image.data;
  for(let i=0;i<values.length;i++){
    rgba[4*i+3]=255;
    if(!range||!Number.isFinite(d.depth_mm[i])||d.depth_mm[i]<=0||!Number.isFinite(values[i]))continue;
    let t=Math.max(0,Math.min(1,(values[i]-range[0])/(range[1]-range[0])));if(reverse)t=1-t;
    const at=t*(mapPalette.length-1),left=Math.min(mapPalette.length-2,Math.floor(at)),fraction=at-left;
    for(let c=0;c<3;c++)rgba[4*i+c]=Math.round(mapPalette[left][c]*(1-fraction)+mapPalette[left+1][c]*fraction);
  }
  ctx.putImageData(image,0,0);return canvas.toDataURL('image/png');
}
function refreshColorMaps(){
  const d=state.depth;if(!d)return;
  const z=[],dis=[];
  for(let i=0;i<d.depth_mm.length;i++)if(Number.isFinite(d.depth_mm[i])&&d.depth_mm[i]>0){
    z.push(d.depth_mm[i]);if(Number.isFinite(d.disparity_px[i]))dis.push(d.disparity_px[i]);
  }
  const automatic=$('map-scale').value==='auto';
  const zr=automatic?displayRange(z,50):[200,3000],dr=automatic?displayRange(dis,2):[0,192];
  state.colorMaps={automatic,depth:{url:colorizeMap(d.depth_mm,zr,false),range:zr},disparity:{url:colorizeMap(d.disparity_px,dr,true),range:dr}};
  $('depth-thumb').src=state.colorMaps.depth.url;$('depth-preview').hidden=false;$('depth-empty').hidden=true;
  $('depth-near').textContent=zr?'近 '+(zr[0]/10).toFixed(1)+' cm':'无有效深度';
  $('depth-far').textContent=zr?'远 '+(zr[1]/10).toFixed(1)+' cm':'—';
  updateColorLegend();
  if(['depth','disparity'].includes(state.view))$('result-image').src=state.colorMaps[state.view].url;
}
function updateColorLegend(){
  const maps=state.colorMaps,kind=state.view,map=maps&&maps[kind];
  $('map-legend').hidden=!map;if(!map)return;
  const automatic=maps.automatic,unit=kind==='depth'?' cm':' px',divisor=kind==='depth'?10:1;
  $('map-scale-title').textContent=(kind==='depth'?'深度':'视差')+' · '+(automatic?'当前照片自动色阶':'固定色阶');
  $('view-badge').textContent=kind==='disparity'?'原始视差 · '+(automatic?'自动色阶':'固定色阶'):(automatic?'自动色阶':'固定色阶');
  if(!map.range){$('map-near').textContent='无有效数值';$('map-mid').textContent='';$('map-far').textContent='';return;}
  const [low,high]=map.range,near=kind==='depth'?low:high,far=kind==='depth'?high:low;
  $('map-near').textContent='近 '+(near/divisor).toFixed(1)+unit;
  $('map-mid').textContent=((low+high)/2/divisor).toFixed(1)+unit;
  $('map-far').textContent='远 '+(far/divisor).toFixed(1)+unit;
}
$('map-scale').addEventListener('change',refreshColorMaps);

function setView(name){
  window.videoReplay?.close();
  if(!views[name]||(name!=='live'&&!state.current))return;
  state.view=name;const v=views[name];
  $('view-title').textContent=v.title;$('view-kicker').textContent=v.kicker;$('view-badge').textContent=v.tag;
  $('selected-view').textContent=v.short;$('stage-guide').textContent=v.guide;
  $('preview').hidden=name!=='live';$('viewer').hidden=name!=='model';
  $('result-image').hidden=name==='live'||name==='model';$('model-card').hidden=name!=='model';
  $('crosshair').hidden=true;$('stage-empty').hidden=true;
  $('stage-notice').hidden=!(state.busy&&name==='live');
  const image=$('result-image');image.classList.toggle('queryable',['left','depth','disparity'].includes(name));
  if(v.file){image.src=state.colorMaps?.[name]?.url||path(v.file);image.alt=v.title;}
  if(name==='photo'){image.src=path('photo_'+state.photoMode+'.png');image.alt='所拍照片 · '+filterNames[state.photoMode];$('view-title').textContent=image.alt;}
  if(name==='live')$('view-title').textContent='实时预览 · '+filterNames[$('preview-mode').value];
  document.querySelectorAll('[data-view]').forEach(el=>{const selected=el.dataset.view===name;el.classList.toggle('selected',selected);el.setAttribute('aria-pressed',String(selected));});
  $('save-view').disabled=!state.current;
  if(name==='model')requestAnimationFrame(()=>send({action:'redraw'}));
  updateVisualStat();updateColorLegend();
}
function updateVisualStat(){
  $('visual-stat').hidden=state.view==='live';
  if(state.view==='live'){$('visual-stat').textContent='';return;}
  if(window.videoReplay?.active){$('visual-stat').textContent='录制回放 · 640 × 480 / 每眼';return;}
  const r=state.result;if(!r){$('visual-stat').textContent='Fast · 单次拍照';return;}
  if(state.view==='photo'){$('visual-stat').textContent='同一张照片 · 左右画面并排';return;}
  $('visual-stat').textContent=state.view==='model'?r.valid_pixels.toLocaleString()+' 个点 · '+r.triangles.toLocaleString()+' 个三角面':'320 × 360 / 每眼';
}
function resetReadout(){
  state.pixel=null;$('picked-depth').innerHTML='—<small> cm</small>';$('picked-pixel').textContent='—';$('picked-disparity').textContent='— px';$('picked-xyz').hidden=true;$('crosshair').hidden=true;
  $('picked-help').textContent='点击深度图、校正左图或三维模型查询。深度来自最近照片，不随实时预览更新。';
}
function showPixel(x,y,xyz){
  const d=state.depth;if(!d)return;
  x=Math.max(0,Math.min(d.width-1,Math.floor(x)));y=Math.max(0,Math.min(d.height-1,Math.floor(y)));
  state.pixel={x,y};const i=y*d.width+x,z=d.depth_mm[i],disparity=d.disparity_px[i];
  $('picked-pixel').textContent='('+x+', '+y+')';$('picked-disparity').textContent=Number.isFinite(disparity)?disparity.toFixed(3)+' px':'— px';
  $('picked-depth').innerHTML=z>0?(z/10).toFixed(2)+'<small> cm</small>':'无效';
  $('picked-xyz').hidden=!(z>0&&xyz&&xyz.every(Number.isFinite));
  if(!$('picked-xyz').hidden)$('picked-xyz').textContent='X '+(xyz[0]/10).toFixed(2)+' / Y '+(xyz[1]/10).toFixed(2)+' / Z '+(xyz[2]/10).toFixed(2)+' cm';
  $('picked-help').textContent=z>0?'当前为最近照片的光轴深度 Z，视差和深度数值保持原样。':'这个像素没有有效深度，黑色位置不会生成有效点云。';
  send({pixel:i});
}
function imagePoint(event,image){
  if(!image.naturalWidth||!image.naturalHeight)return null;
  const r=image.getBoundingClientRect(),scale=Math.min(r.width/image.naturalWidth,r.height/image.naturalHeight);
  const width=image.naturalWidth*scale,height=image.naturalHeight*scale,left=r.left+(r.width-width)/2,top=r.top+(r.height-height)/2;
  const x=event.clientX-left,y=event.clientY-top;if(x<0||y<0||x>=width||y>=height)return null;
  return {x:x/width*state.depth.width,y:y/height*state.depth.height};
}
$('depth-thumb').addEventListener('click',event=>{if(!state.depth)return;const p=imagePoint(event,event.currentTarget);if(p)showPixel(p.x,p.y);});
$('result-image').addEventListener('click',event=>{
  if(!state.depth||!['left','depth','disparity'].includes(state.view))return;
  const p=imagePoint(event,event.currentTarget);if(!p)return;showPixel(p.x,p.y);
  const stage=$('stage').getBoundingClientRect();$('crosshair').style.left=(event.clientX-stage.left)+'px';$('crosshair').style.top=(event.clientY-stage.top)+'px';$('crosshair').hidden=false;
});

async function loadResult(result){
  state.current=result.job_id;state.result=result;state.depth=null;state.colorMaps=null;state.frameReady=false;resetReadout();
  $('saved-render').hidden=true;$('export-status').textContent='';
  $('photo-label').textContent=(result.video_source?'视频第 '+(result.video_source.frame+1)+' 帧 · '+result.video_source.timestamp_seconds.toFixed(3)+' 秒 · ':result.replay_only?'同照片回放验证 ':'照片 ')+state.current.slice(0,8)+' · '+state.current.slice(-6);
  $('depth-source').textContent='照片 '+state.current.slice(0,8);
  $('depth-preview').hidden=true;$('depth-empty').hidden=false;$('depth-empty').textContent='正在载入深度图…';
  $('time-infer').textContent=result.forward_seconds.toFixed(2)+' 秒';$('time-conv').textContent=result.conv_pl?result.conv_pl.device_seconds.toFixed(2)+' 秒 / '+result.conv_pl.calls+' 层':'—';$('time-deconv').textContent=result.pl.device_seconds.toFixed(2)+' 秒 / '+result.pl.calls+' 层';$('time-load').textContent=result.model_resident?'已常驻':result.load_seconds.toFixed(2)+' 秒';$('time-total').textContent=result.total_seconds.toFixed(2)+' 秒';
  const copy=(result.conv_pl?.copyin_seconds||0)+(result.conv_pl?.copyout_seconds||0)+(result.pl?.copyin_seconds||0)+(result.pl?.copyout_seconds||0);
  $('time-copy').textContent=copy.toFixed(3)+' 秒';$('time-ps').textContent=(result.forward_seconds-copy-(result.conv_pl?.device_seconds||0)-(result.pl?.device_seconds||0)).toFixed(2)+' 秒';
  for(const [id,value] of [['time-rectify',result.pl_rectification_seconds],['time-geometry',result.geometry_seconds],['time-receive',result.pc_receive_seconds],['time-export',result.pc_export_seconds]])$(id).textContent=Number.isFinite(value)?value.toFixed(3)+' 秒':'—';
  $('geometry-label').textContent=result.geometry_pl?'PL 坐标与搬运':'PS 三维坐标';
  $('time-geometry').title=result.geometry_pl?'PL 核心 '+(result.geometry_pl.device_seconds*1000).toFixed(2)+' ms；本项包含数据搬运与检查':'';
  $('time-live').textContent=result.processing_preview?.display_mode==='captured_still'?'所拍静态照片':result.processing_preview?.mean_fps?result.processing_preview.mean_fps.toFixed(1)+' FPS · 并行运行':'—';
  $('point-count').textContent=result.valid_pixels.toLocaleString();$('face-count').textContent=result.triangles.toLocaleString();
  for(const [id,file] of Object.entries({points:'points.ply',surface:'dense_surface.ply',open3d:'viewer.html',report:'report.json'})){
    $(id).href=path(file);$(id).classList.remove('disabled');$(id).setAttribute('aria-disabled','false');
  }
  document.querySelectorAll('[data-view]').forEach(el=>el.disabled=false);
  $('photo-mode').disabled=false;
  window.photoTiming.mark('web_result_seen',result.job_id);
  window.photoTiming.mark('viewer_load_started',result.job_id);
  $('viewer').src=path('viewer.html')+'?embed';setView(state.view);
  let response=await fetch(path('depth_values.bin')),data;
  if(response.ok){
    const buffer=await response.arrayBuffer(),header=new DataView(buffer);
    if(buffer.byteLength!==16+115200*16||header.getUint32(0,true)!==0x31505444||header.getUint32(4,true)!==1||header.getUint32(8,true)!==320||header.getUint32(12,true)!==360)throw Error('深度二进制尺寸不匹配');
    data={width:320,height:360,depth_mm:new Float64Array(buffer,16,115200),disparity_px:new Float64Array(buffer,16+115200*8,115200)};
  }else if(response.status===404){response=await fetch(path('depth_values.json'));if(!response.ok)throw Error('深度信息加载失败');data=await response.json();}
  else throw Error('深度信息加载失败');
  if(state.current!==result.job_id)return;
  if(data.width!==320||data.height!==360||data.depth_mm.length!==115200||data.disparity_px.length!==115200)throw Error('深度图尺寸不匹配');
  state.depth=data;refreshColorMaps();window.photoTiming.mark('depth_maps_ready',result.job_id);window.wakeFastHdmi?.();
}
async function poll(){
  let pollDelay=500;
  try{
    const response=await fetch('/api/status');if(!response.ok)throw Error('显示服务暂时不可用');const s=await response.json(),previousBusy=state.busy;
    if(['geometry','restore_preview','export_3d'].includes(s.stage)||s.hdmi?.waiting_for_render)pollDelay=100;
    window.updateSectionStatus?.(s.section);state.busy=s.busy;$('capture').disabled=state.busy||state.pending||window.videoReplay?.recording;
    $('status').className='status'+(s.error?' error':'');
    $('status').textContent=s.error||((labels[s.stage]||s.stage)+(s.busy?' · 已用 '+s.elapsed_seconds+' 秒':s.result&&s.stage==='idle'?' · 已载入最近照片':''));
    $('capture-tag').textContent=s.error?'请检查':s.busy?'处理中':'已就绪';
    $('header-state').textContent=s.error?'处理异常':s.busy?'正在处理 · '+s.elapsed_seconds+' s':'已就绪';
    $('header-dot').className='dot'+(s.error?' error':s.busy?' busy':'');
    $('stage-notice').hidden=!(s.busy&&state.view==='live');
    if(s.result&&s.result.job_id!==state.current)await loadResult(s.result);
    if(previousBusy&&!s.busy&&!s.error&&s.stage==='ready'&&s.result)setView('model');
    $('preview-mode').disabled=state.busy||window.videoReplay?.recording;$('photo-mode').disabled=state.busy||!state.current||window.videoReplay?.recording;
    const hdmi=s.hdmi,selection=hdmi?hdmi.generation+':'+hdmi.display_epoch:null;
    if(hdmi?.preview_mode in filterNames&&document.activeElement!==$('preview-mode'))$('preview-mode').value=hdmi.preview_mode;
    if(selection&&selection!==state.displaySelection){
      state.displaySelection=selection;
      if(!state.busy&&hdmi.job_id===state.current&&hdmi.view?.startsWith('photo_')){
        const mode=hdmi.view.slice(6);if(mode in filterNames){state.photoMode=mode;$('photo-mode').value=mode;setView('photo');}
      }else if(!state.busy&&hdmi.view==='preview')setView('live');
    }
    window.photoTiming.show(s.timing);
    if(window.updateFastHdmi)window.updateFastHdmi(s.hdmi);
  }catch(error){$('status').className='status error';$('status').textContent=error.message;$('header-state').textContent='连接中';$('header-dot').className='dot error';}
  setTimeout(poll,pollDelay);
}
$('capture').addEventListener('click',async()=>{
  if(state.busy||state.pending)return;state.pending=true;$('capture').disabled=true;
  try{
    const response=await fetch('/api/capture',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:'{}'});
    const result=await response.json();if(!response.ok)throw Error(result.error||'拍照没有启动');
    state.busy=true;setView('live');$('status').className='status';$('status').textContent='正在拍摄新的左右画面…';
  }catch(error){$('status').className='status error';$('status').textContent=error.message;}
  finally{state.pending=false;$('capture').disabled=state.busy;}
});
async function selectDisplay(op,mode){
  if(state.busy)return;
  const body={op,mode};if(op==='photo')body.job_id=state.current;
  try{
    const response=await fetch('/api/display',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'显示切换失败');
    window.updateFastHdmi?.(result);
  }catch(error){$('hdmi-note').textContent='HDMI：'+error.message;}
}
document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>{
  setView(el.dataset.view);
  if(el.dataset.view==='photo')selectDisplay('photo',state.photoMode);
  else if(el.dataset.view==='live')selectDisplay('preview',$('preview-mode').value);
}));
$('return-preview').addEventListener('click',()=>{setView('live');selectDisplay('preview',$('preview-mode').value);});
$('preview-mode').addEventListener('change',()=>{setView('live');selectDisplay('preview',$('preview-mode').value);});
$('photo-mode').addEventListener('change',()=>{state.photoMode=$('photo-mode').value;setView('photo');selectDisplay('photo',state.photoMode);});
controls.forEach(el=>el.addEventListener('input',()=>{
  if(el.id==='model-size')$('point-size-value').textContent=Number(el.value).toFixed(1);
  send({control:el.dataset.control,value:el.value});
}));
document.querySelectorAll('[data-action]').forEach(el=>el.addEventListener('click',()=>send({action:el.dataset.action})));
async function save(data,name){
  const job=state.current;if(!job)return;
  try{
    $('export-status').textContent='正在保存画面…';
    const png=Uint8Array.from(atob(data.split(',')[1]),c=>c.charCodeAt(0));
    const response=await fetch('/api/render-export',{method:'POST',headers:{'Content-Type':'image/png','X-Viewer-Token':window.FAST_UI_TOKEN,'X-Photo-Id':job},body:png});
    const result=await response.json();if(!response.ok)throw Error(result.error||'PNG 保存失败');
    if(state.current!==job)return;
    $('saved-render').href=result.url;$('saved-render').download=name;$('saved-render').hidden=false;
    $('export-status').textContent='PNG 已保存到电脑上的当前照片目录。';
  }catch(error){$('export-status').textContent=error.message;}
}
$('save-view').addEventListener('click',()=>{
  if(state.view==='model'){send({action:'save_png'});return;}
  const image=state.view==='live'?$('preview'):$('result-image');if(!image.naturalWidth)return;
  const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;canvas.getContext('2d').drawImage(image,0,0);
  save(canvas.toDataURL('image/png'),'Fast_'+(state.current||'preview')+'_'+state.view+'.png');
});
$('viewer').addEventListener('load',()=>{
  // Explicit handshake also covers a ready message lost during iframe replacement.
  $('viewer').contentWindow.postMessage({type:'fast_viewer_control',action:'hello'},location.origin);
});
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==$('viewer').contentWindow||event.data?.type!=='fast_viewer_state')return;
  const m=event.data;
  if(m.kind==='ready'){state.frameReady=true;syncControls();window.photoTiming.mark('viewer_ready',state.current);window.wakeFastHdmi?.();}
  else if(m.kind==='selection'&&Number.isInteger(m.pixel)&&state.depth){
    const x=m.pixel%state.depth.width,y=Math.floor(m.pixel/state.depth.width);if(y<state.depth.height){
      // Readout uses the original saved depth and disparity, never a display estimate.
      const xyz=Array.isArray(m.xyz_mm)?m.xyz_mm:null;
      const d=state.depth,i=m.pixel,z=d.depth_mm[i];state.pixel={x,y};
      $('picked-pixel').textContent='('+x+', '+y+')';$('picked-disparity').textContent=Number.isFinite(d.disparity_px[i])?d.disparity_px[i].toFixed(3)+' px':'— px';
      $('picked-depth').innerHTML=z>0?(z/10).toFixed(2)+'<small> cm</small>':'无效';
      $('picked-xyz').hidden=!(z>0&&xyz&&xyz.every(Number.isFinite));if(!$('picked-xyz').hidden)$('picked-xyz').textContent='X '+(xyz[0]/10).toFixed(2)+' / Y '+(xyz[1]/10).toFixed(2)+' / Z '+(xyz[2]/10).toFixed(2)+' cm';
      $('picked-help').textContent=z>0?'当前为最近照片的光轴深度 Z，视差和深度数值保持原样。':'这个像素没有有效深度。';
    }
  }else if(m.kind==='controls'){
    for(const el of controls){const value=m.controls?.[el.dataset.control];if(!value)continue;el.disabled=value.disabled;if(document.activeElement!==el)el.value=value.value;}
    if(m.stats&&state.view==='model')$('visual-stat').textContent=m.stats;
  }else if(m.kind==='png'&&typeof m.data==='string'&&m.data.startsWith('data:image/png;base64,'))save(m.data,'Fast_'+state.current+'_3d.png');
});
let previewCursor='',previewUrl='',previewFrames=0,previewWindowFrames=0,previewWindow=performance.now(),previewPending=null;
function previewRequest(cursor){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1800);
  return fetch('/preview.jpg'+(cursor?'?after='+cursor:''),{cache:'no-store',signal:controller.signal}).then(async response=>{
    if(!response.ok)throw Error('Preview unavailable');
    const seq=response.headers.get('X-Frame-Sequence'),epoch=response.headers.get('X-Frame-Epoch');
    return {seq:seq,epoch:epoch,source:response.headers.get('X-Frame-Source'),mode:response.headers.get('X-Frame-Mode'),stale:response.headers.get('X-Frame-Stale')==='1',cursor:seq+','+epoch,blob:await response.blob()};
  }).finally(()=>clearTimeout(timer));
}
async function preview(){
  let delay=0;
  try{
    if(!previewPending){previewPending=previewRequest(previewCursor);previewPending.catch(()=>{});}
    const pending=previewPending;pending.catch(()=>{});
    const frame=await pending;previewPending=null;
    if(frame.stale){delay=100;return}
    const live=frame.source==='camera'&&frame.seq!==null&&frame.epoch!==null;
    if(!live||frame.cursor!==previewCursor){
      if(live){previewCursor=frame.cursor;previewPending=previewRequest(previewCursor);previewPending.catch(()=>{});}
      const next=URL.createObjectURL(frame.blob),decoded=new Image();decoded.src=next;
      try{await decoded.decode()}catch(e){URL.revokeObjectURL(next);throw e}
      const previous=previewUrl;previewUrl=next;$('preview').src=next;if(previous)URL.revokeObjectURL(previous);
      if(live){
        previewFrames++;document.body.dataset.previewFrames=String(previewFrames);
        document.body.dataset.previewSequence=frame.seq;document.body.dataset.previewEpoch=frame.epoch;document.body.dataset.previewMode=frame.mode;
        document.body.dataset.previewWidth=String(decoded.naturalWidth);document.body.dataset.previewHeight=String(decoded.naturalHeight);
        const now=performance.now();if(now-previewWindow>=3000){document.body.dataset.previewFps=((previewFrames-previewWindowFrames)*1000/(now-previewWindow)).toFixed(1);previewWindow=now;previewWindowFrames=previewFrames;updateVisualStat();}
      }else{previewCursor='';delay=150;previewWindow=performance.now();previewWindowFrames=previewFrames;}
    }else delay=10;
  }catch(e){delay=300;previewCursor='';previewPending=null}finally{setTimeout(preview,delay)}
}
poll();preview();

// Crop the display only. JPEG capture, recording and reconstruction stay full frame.
(()=>{
  const stage=$('stage'),image=$('preview'),canvas=$('preview-zoom'),reset=$('preview-zoom-reset'),ctx=canvas.getContext('2d');
  let view={scale:1,cx:.5,cy:.5},accepted={...view},sending=false,pending=null,drag=null,dirty=false,touched=false;
  const active=()=>state.view==='live'&&!image.hidden&&!state.busy&&!window.videoReplay?.active;
  function rect(){
    const width=image.naturalWidth||1280,height=image.naturalHeight||480;
    const w=Math.max(1,Math.round(width/view.scale)),h=Math.max(1,Math.round(height/view.scale));
    return {width,height,w,h,x:Math.max(0,Math.min(width-w,Math.round(view.cx*width-w/2))),y:Math.max(0,Math.min(height-h,Math.round(view.cy*height-h/2)))};
  }
  function paint(){
    dirty=false;const visible=active()&&view.scale>1.001;
    canvas.hidden=!visible;reset.hidden=!visible;stage.classList.toggle('preview-magnified',visible);
    if(!visible||!image.naturalWidth)return;
    const r=rect();if(canvas.width!==r.width||canvas.height!==r.height){canvas.width=r.width;canvas.height=r.height;}
    ctx.imageSmoothingEnabled=false;ctx.drawImage(image,r.x,r.y,r.w,r.h,0,0,r.width,r.height);
    canvas.dataset.viewport=JSON.stringify({...view,roi:[r.x,r.y,r.w,r.h]});
    reset.textContent=view.scale.toFixed(1)+'× · 恢复 1×';
  }
  function redraw(){if(!dirty){dirty=true;requestAnimationFrame(paint);}}
  function normalized(){const half=.5/view.scale;view.cx=Math.max(half,Math.min(1-half,view.cx));view.cy=Math.max(half,Math.min(1-half,view.cy));}
  async function flush(){
    if(sending||!pending)return;
    const next=pending;pending=null;sending=true;
    try{
      const response=await fetch('/api/preview-zoom',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify(next)});
      const reply=await response.json();if(!response.ok)throw Error(reply.error||'HDMI 缩放同步失败');
      accepted={scale:reply.scale,cx:reply.cx,cy:reply.cy};reset.title='恢复完整画面';
    }catch(error){pending=null;view={...accepted};redraw();$('stage-guide').textContent='缩放同步失败，请稍后重试';}
    finally{sending=false;if(pending)flush();}
  }
  let syncTimer=null;
  function change(){touched=true;normalized();redraw();pending={...view};if(!syncTimer)syncTimer=setTimeout(()=>{syncTimer=null;flush();},50);}
  function point(event){
    const box=stage.getBoundingClientRect(),ratio=Math.min(box.width/(image.naturalWidth||1280),box.height/(image.naturalHeight||480));
    const width=(image.naturalWidth||1280)*ratio,height=(image.naturalHeight||480)*ratio;
    return {u:(event.clientX-box.left-(box.width-width)/2)/width,v:(event.clientY-box.top-(box.height-height)/2)/height,width,height};
  }
  stage.addEventListener('wheel',event=>{
    if(!active()||event.target===reset||!image.naturalWidth)return;
    const p=point(event);if(p.u<0||p.u>1||p.v<0||p.v>1)return;
    event.preventDefault();const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?stage.clientHeight:1);
    const previous=view.scale,next=Math.max(1,Math.min(6,previous*Math.exp(-Math.max(-250,Math.min(250,delta))*.002)));
    view.cx+=(p.u-.5)*(1/previous-1/next);view.cy+=(p.v-.5)*(1/previous-1/next);view.scale=next;change();
  },{passive:false});
  function restore(){if(!active())return;view={scale:1,cx:.5,cy:.5};change();}
  reset.addEventListener('click',restore);
  stage.addEventListener('dblclick',event=>{if(active()){event.preventDefault();restore();}});
  stage.addEventListener('pointerdown',event=>{
    if(!active()||view.scale<=1||event.button!==0||event.target===reset)return;
    const p=point(event);if(p.u<0||p.u>1||p.v<0||p.v>1)return;
    event.preventDefault();drag={id:event.pointerId,x:event.clientX,y:event.clientY,cx:view.cx,cy:view.cy,width:p.width,height:p.height};stage.setPointerCapture(event.pointerId);stage.classList.add('preview-panning');
  });
  stage.addEventListener('pointermove',event=>{if(!drag||drag.id!==event.pointerId)return;view.cx=drag.cx-(event.clientX-drag.x)/drag.width/view.scale;view.cy=drag.cy-(event.clientY-drag.y)/drag.height/view.scale;change();});
  function release(){drag=null;stage.classList.remove('preview-panning');}
  stage.addEventListener('pointerup',release);stage.addEventListener('pointercancel',release);stage.addEventListener('lostpointercapture',release);
  image.addEventListener('dragstart',event=>{if(active()&&view.scale>1)event.preventDefault();});
  image.addEventListener('load',redraw);
  new MutationObserver(()=>{if(!active())release();redraw();}).observe(image,{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(redraw).observe($('video-playback'),{attributes:true,attributeFilter:['hidden']});
  new MutationObserver(redraw).observe($('stage-notice'),{attributes:true,attributeFilter:['hidden']});
  fetch('/api/preview-zoom').then(r=>{if(!r.ok)throw Error('unavailable');return r.json();}).then(v=>{if(!touched&&!pending&&!sending){view={scale:v.scale,cx:v.cx,cy:v.cy};accepted={...view};redraw();}}).catch(()=>{});
})();
