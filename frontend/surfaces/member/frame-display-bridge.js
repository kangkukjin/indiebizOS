window.addEventListener('message',function(event){
 if(event.source!==parent||event.data?.memberFrame!=='display')return;
 const value=event.data;
 const run=value.rollback?IndieDisplay.rollback(value.version):IndieDisplay.apply(value.display);
 Promise.resolve(run).then(result=>parent.postMessage({memberFrame:'display-result',token:value.token,result},'*'),error=>parent.postMessage({memberFrame:'display-result',token:value.token,error:String(error.message||error)},'*'));
});
