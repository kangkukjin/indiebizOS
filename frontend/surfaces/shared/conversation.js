import conversationHeader from './conversation.json';
/* Shared conversation display rules. No task requests, permissions or subscriptions. ES5 for lite. */
(function(root,header){
  var rules={
    header:header,
    pageSize:50,
    day:function(value){var d=value instanceof Date?value:new Date(value||'');function pad(n){return n<10?'0'+n:String(n)}return isNaN(d.getTime())?'':d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())},
    visibleStart:function(length,start,older){
      var size=this.pageSize;
      return Math.max(0,Math.min(length,start==null?length-size:start-(older?size:0)));
    },
    matchesWord:function(text,query){return String(text||'').toLowerCase().indexOf(String(query||'').toLowerCase().trim())>=0},
    insertWord:function(value,id){return value+(value&&!/\s$/.test(value)?' ':'')+'['+id+']{} '},
    arrange:function(container,ids){
      if(!container)return;
      header.forEach(function(item){var button=document.getElementById(ids[item.id]);if(button){button.textContent=(item.prefix||'')+(root.__ui?root.__ui.source('conversation',item.label):item.label);container.appendChild(button)}});
    }
  };
  root.getConversation=function(){return rules};
})(typeof window!=='undefined'?window:globalThis,conversationHeader);
/* --- ESM export (classic-script hosts omit only this tail) --- */
function getConversation(){return (typeof window!=='undefined'?window:globalThis).getConversation()}
export {getConversation};
