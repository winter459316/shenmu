(()=>{
 const q=id=>document.getElementById(id),owner=crypto.randomUUID().replaceAll('-','');
 let active=false,busy=false,running=false,queued=false,seq=0,epoch=0,meta=null,timer=0,planeSpan=0;
 const notice=q('cut-status'),controls=q('cut-controls');
 function message(m,transfer=[]){q('viewer').contentWindow?.postMessage({type:'fast_section_control',...m},location.origin,transfer);}
 async function api(op,args={}){const r=await fetch('/api/section/'+op,{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify({owner,...args})});const data=await r.json();if(!r.ok)throw Error(data.error||'截面操作失败');return data;}
 function show(text){notice.textContent=text;}
 function buttons(){q('cut-toggle').disabled=busy||state.busy||!state.current;q('cut-toggle').textContent=active?'退出截面':'进入 PL 截面';controls.hidden=!active;q('cut-thickness').disabled=active||busy;}
 function appearance(){const ghost=q('cut-ghost').checked,opacity=Number(q('cut-opacity').value)/100;q('cut-opacity').disabled=!ghost;q('cut-opacity-value').textContent=Math.round(opacity*100)+'%';message({action:'appearance',ghost,opacity,cap:q('cut-cap').checked,guide:q('cut-plane-guide').checked});}
 function normal(){const a=Number(q('cut-azimuth').value)*Math.PI/180,b=Number(q('cut-elevation').value)*Math.PI/180;return [Math.cos(b)*Math.cos(a),Math.cos(b)*Math.sin(a),Math.sin(b)];}
 function projectedRange(){const n=normal(),lo=meta.bounds_mm[0],hi=meta.bounds_mm[1],values=[];for(const x of [lo[0],hi[0]])for(const y of [lo[1],hi[1]])for(const z of [lo[2],hi[2]])values.push(x*n[0]+y*n[1]+z*n[2]);return [Math.min(...values),Math.max(...values)];}
 function focusPosition(){const n=normal(),[lo,hi]=projectedRange();return 100*(meta.focus_mm.reduce((s,x,i)=>s+x*n[i],0)-lo)/(hi-lo);}
 async function run(){
   if(!active||running)return;running=true;queued=false;const myEpoch=epoch,mySeq=++seq;
   try{
     const result=await api('run',{job_id:state.current,seq:mySeq,normal:normal(),position:Number(q('cut-position').value),flip:q('cut-flip').checked});
     if(active&&myEpoch===epoch){planeSpan=result.geometry.pixel_mm*512;message({action:'result',...result});show(result.pixels?`PL 求交与封盖 ${result.device_ms.toFixed(1)} ms · 更新 ${result.roundtrip_ms.toFixed(0)} ms · ${result.segments.toLocaleString()} 条交线 · ${result.pixels.toLocaleString()} 个填充像素`:'当前切面没有可填充区域，可拖动位置或调整方向。');q('cut-scale').textContent=`封盖 512 × 512 · 每像素 ${result.geometry.pixel_mm.toFixed(2)} mm · 假设厚度 ${meta.thickness_mm} mm`;}
   }catch(error){if(myEpoch===epoch)show(error.message);}
   finally{running=false;if(queued&&active)run();}
 }
 function change(){q('cut-position-value').textContent=Number(q('cut-position').value).toFixed(1)+'%';queued=true;if(!timer)timer=setTimeout(()=>{timer=0;run();},0);}
 async function leave(){
   if(busy)return;busy=true;epoch++;buttons();show('正在退出截面…');
   try{await api('exit');active=false;message({action:'disable'});show('已退出截面，原始模型已恢复。');}
   catch(e){show(e.message);}finally{busy=false;buttons();}
 }
 q('cut-toggle').addEventListener('click',async()=>{
   if(active){await leave();return;}busy=true;buttons();show('正在准备截面显示…');
   try{
     meta=await api('enter',{job_id:state.current,thickness_mm:Number(q('cut-thickness').value)});
     const response=await fetch('/api/section/extra?owner='+owner);if(!response.ok)throw Error('截面显示模型下载失败');const buffer=await response.arrayBuffer();if(buffer.byteLength!==meta.extra_bytes)throw Error('截面模型长度不匹配');
     message({action:'model',buffer,meta},[buffer]);active=true;epoch++;seq=0;state.frameReady=true;setView('model');send({control:'mode',value:'mesh'});
     q('cut-axis').value='x';q('cut-azimuth').value=0;q('cut-elevation').value=0;q('cut-position').value=focusPosition();message({action:'dragmode',enabled:q('cut-drag-mode').checked});appearance();change();
   }catch(e){show(e.message);try{await api('exit');}catch(_){}active=false;message({action:'disable'});}
   finally{busy=false;buttons();}
 });
 for(const id of ['cut-position','cut-azimuth','cut-elevation','cut-flip'])q(id).addEventListener('input',change);
 for(const id of ['cut-ghost','cut-opacity','cut-cap','cut-plane-guide'])q(id).addEventListener('input',appearance);
 q('cut-drag-mode').addEventListener('change',()=>message({action:'dragmode',enabled:q('cut-drag-mode').checked}));
 q('cut-axis').addEventListener('change',()=>{const axis=q('cut-axis').value,angles={x:[0,0],y:[90,0],z:[0,90],oblique:[35,25]}[axis];q('cut-azimuth').value=angles[0];q('cut-elevation').value=angles[1];if(meta)q('cut-position').value=focusPosition();change();});
 window.addEventListener('message',event=>{
   if(event.origin!==location.origin||event.source!==q('viewer').contentWindow||event.data?.type!=='fast_section_viewer')return;
   const m=event.data;if(m.kind==='drag'&&active){const [lo,hi]=projectedRange(),scale=planeSpan?Math.min(1,planeSpan/(hi-lo)):1;q('cut-position').value=Math.max(0,Math.min(100,Number(q('cut-position').value)+m.delta*scale));change();}
 });
 window.updateSectionStatus=s=>{
   if(!s)return;
   if(s.error&&!active&&!busy)show(s.error);
   if(active&&!s.active&&!s.switching&&!busy){active=false;epoch++;message({action:'disable'});show('已退出截面。');}
   buttons();
 };
 setInterval(async()=>{if(!active||busy)return;try{await api('heartbeat');}catch(e){show('截面连接：'+e.message);}},5000);
 window.addEventListener('pagehide',()=>{if(active)fetch('/api/section/exit',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify({owner})}).catch(()=>{});});
 buttons();
})();
