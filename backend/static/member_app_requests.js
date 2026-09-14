/* The renderer keeps its existing view grammar; every web execution is a server action ID. */
const originalBuildAction=buildAction,originalRowAction=rowAction,legacyMemberIbl=ibl,legacyFillOptions=fillOptions;
function clientSpec(value){
 const id=typeof value==='string'&&value.startsWith('client-action:')?value.slice(14):value?.action_id;
 if(!id)return null;
 for(const app of INSTRUMENTS){if(app.client_actions?.[id])return {id,...app.client_actions[id]}}
 throw Error('앱을 새로고침한 뒤 다시 실행하세요');
}
function clientCall(value,inputs={},row){
 const spec=clientSpec(value);if(!spec)return null;
 const all={...spec.defaults,...gatherInputs(),...(value?.args||{}),...inputs};
 const args=Object.fromEntries(spec.inputs.map(k=>[k,all[k]??'']));
 if(spec.rows.length)args._row=Object.fromEntries(spec.rows.map(k=>[k,row?jget(row,k)??'':value?.args?._row?.[k]??'']));
 return {action_id:spec.id,args,title:CUR.inst?.name||'앱 실행',app_id:CUR.inst?.id};
}
buildAction=function(value,inputs){return clientCall(value,inputs)||originalBuildAction(value,inputs)};
rowAction=function(value,row){return clientCall(value,{},row)||originalRowAction(value,row)};
ibl=function(value){
 const request=clientCall(value);
 if(!request){if(INSTRUMENTS.some(a=>a.client_actions))return Promise.reject(Error('현재 공개된 앱 동작이 아닙니다'));return legacyMemberIbl(value)}
 return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({memberFrame:'request',id,...request},'*')});
};
memberAppRequest=function(spec){return ibl('client-action:'+spec.client_action_id)};
fillOptions=async function(inp){
 const spec=clientSpec(inp.options_action);if(!spec)return legacyFillOptions(inp);
 const sel=document.getElementById('in_'+inp.key);if(!sel)return;
 const call=clientCall(inp.options_action);
 if(spec.inputs.some(k=>!call.args[k])){setOptions(sel,[],null);return}
 sel.disabled=true;
 try{const d=await ibl(call);if(document.getElementById('in_'+inp.key)!==sel)return;setOptions(sel,normalizeOptions(jget(d,inp.options_from),inp),inp.default)}
 catch(e){document.getElementById('instOut').textContent=e.message}finally{sel.disabled=false}
};
const legacySelChanged=selChanged;
selChanged=function(key){if(!CUR.inst?.client_actions)return legacySelChanged(key);for(const inp of CUR.mode?.inputs||[]){if(clientSpec(inp.options_action)?.inputs.includes(key))fillOptions(inp)}};
_upFileObj=async function(key,file,el){
 if(!file)return;
 const label=document.getElementById('infl_'+key),input=document.getElementById('in_'+key);
 try{const result=await new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({memberFrame:'import',id,file},'*')});input.value=result.path;selChanged(key);if(label)label.textContent=file.name}
 catch(e){if(label)label.textContent=e.message;if(el)el.value=''}
};
