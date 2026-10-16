/* The opaque app frame keeps its request queue, editors and media alive. */
(function(){
 let waiting=[],serial=0;const pending=new Map();
 function send(value){return new Promise((resolve,reject)=>{
  const frame=document.getElementById('appFrame');const token='display-'+(++serial);
  function post(){pending.set(token,{resolve,reject,source:frame.contentWindow});frame.contentWindow.postMessage({memberFrame:'display',token,...value},'*')}
  if(frameReady)post();else waiting.push(post);
 })}
 window.addEventListener('message',event=>{
  if(event.source!==document.getElementById('appFrame').contentWindow)return;
  const value=event.data||{};
  if(value.memberFrame==='ready'){const queue=waiting;waiting=[];queue.forEach(fn=>fn())}
  if(value.memberFrame==='display-result'){const request=pending.get(value.token);if(!request||request.source!==event.source)return;pending.delete(value.token);value.error?request.reject(Error(value.error)):request.resolve(value.result)}
 });
 window.IndieFrame={apply:display=>send({display}),rollback:version=>send({rollback:true,version})};
})();
