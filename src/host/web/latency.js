/* Timing only; never starts capture or modifies image data. */
(()=>{
  const client=crypto.randomUUID(),seen=new Set(),queue=[];let timer=null;
  const clock=(async()=>{
    let best=null;
    for(let i=0;i<3;i++){
      const a=performance.now()/1000;
      const response=await fetch('/api/timing-clock');if(!response.ok)throw Error('timing clock unavailable');
      const reply=await response.json(),b=performance.now()/1000;
      const sample={offset:reply.monotonic-(a+b)/2,bound:(b-a)*500};
      if(!best||sample.bound<best.bound)best=sample;
    }
    return best;
  })().catch(()=>null);
  async function flush(){
    timer=null;const sample=await clock;if(!sample){queue.length=0;return;}
    const batch=queue.splice(0),jobs=[...new Set(batch.map(e=>e.job))];
    for(const job of jobs){
      const events=batch.filter(e=>e.job===job).map(e=>({name:e.name,stamp:e.stamp+sample.offset}));
      try{await fetch('/api/timing',{method:'POST',headers:{'Content-Type':'application/json','X-Viewer-Token':window.FAST_UI_TOKEN},body:JSON.stringify({job_id:job,client_id:client,clock_bound_ms:sample.bound,events})});}catch(error){console.warn('Timing delivery failed',error);}
    }
  }
  function mark(name,job){
    if(!job)return;const key=job+':'+name;if(seen.has(key))return;seen.add(key);
    queue.push({job,name,stamp:performance.now()/1000});if(!timer)timer=setTimeout(flush,50);
  }
  const rows=[['board_ready','板端结果可读取'],['pc_observed_board_ready','电脑发现板端完成'],['receive_done','电脑收完结果'],['export_done','电脑连面与导出完成'],['web_result_seen','网页发现新照片'],['depth_maps_ready','深度数据与色彩图就绪'],['viewer_ready','三维查看器就绪'],['web_first_frame','网页三维首帧'],['hdmi_ready','HDMI 四种画面就绪']];
  function show(trace){
    if(!trace)return;
    const box=document.getElementById('latency-values');if(!box)return;box.replaceChildren();
    for(const [key,title] of rows){
      const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');
      dt.textContent=title;dd.textContent=Number.isFinite(trace.events[key])?trace.events[key].toFixed(3)+' 秒':'等待中';row.append(dt,dd);box.append(row);
    }
    document.getElementById('latency-note').textContent='照片 '+trace.job_id.slice(0,8)+' · 从'+(trace.source==='PL_KEY2'?'PL_KEY2 按下':'电脑收到拍照请求')+'起累计计时。跨设备时钟估计误差约 ±'+Math.ceil(trace.board_clock_bound_ms+(trace.browser_clock_bound_ms||0))+' ms。';
    const link=document.getElementById('latency-download');link.hidden=!Number.isFinite(trace.events.export_done);link.href='/captures/'+trace.job_id+'/latency.json';
  }
  window.photoTiming={mark,show};
  window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==document.getElementById('viewer')?.contentWindow||event.data?.type!=='fast_viewer_state')return;
    if(event.data.kind==='timing_first_frame')mark('web_first_frame',event.data.job_id);
  });
})();
