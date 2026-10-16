  function renderLiteSessions(host){
    var $=host.$,chatItems=host.items,chatId=host.id,selectChat=host.select;
    var box=$("chatSessions"), day="";box.innerHTML="";
    for(var i=0;i<chatItems.length;i++){
      var row=chatItems[i],next=getConversation().day(row.updated_at||row.created_at);
      if(next!==day){day=next;var h=document.createElement("h4");h.textContent=day;box.appendChild(h);}
      var button=document.createElement("button");button.className="session";button.textContent=row.title+(row.running?" · 진행 중":"");
      button.setAttribute("aria-current",String(row.id===chatId));
      button.onclick=(function(id){return function(){selectChat(id);};})(row.id);box.appendChild(button);
    }
    if(!chatItems.length)box.textContent="표시할 세션이 없습니다.";

  }

function renderLiteMessages(host){
var $=host.$,esc=host.esc,chatRows=host.rows,chatRunning=host.running,d=host.data,i;
      var log=$("chatlog");log.innerHTML="";
      for(i=0;i<chatRows.length;i++){
        var r=chatRows[i],div=document.createElement("div");div.className="msg "+(r.role==="user"?"user":"ai");
        div.innerHTML='<div class="who">'+esc((r.role==="user"?"나":"시스템 AI")+" · "+String(r.timestamp||"").slice(0,16))+'</div><div class="bub">'+esc(r.content)+'</div>';log.appendChild(div);
      }
      if(chatRunning){var w=document.createElement("div");w.className="wait";w.textContent=(d.turn&&d.turn.stream_content)||"시스템 AI가 생각하는 중…";log.appendChild(w);}
      if(!chatRows.length&&!chatRunning)log.textContent="메시지를 입력해 시작하세요.";
}
