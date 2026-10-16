/* Display lifetime only. Requests, native bridges, timers and application frames stay with their hosts. */
(function(root){
  'use strict';
  if(root.IndieDisplay)return;
  var current=null,previousDisplay=null,refresh=function(){},busy=false,composing=false,locks=0,waiters=[];
  var protectedIds=['message','fileEditor','filePath','appFrame','approvals','memberAudio'];
  function wake(){if(!composing&&!locks){var pending=waiters.splice(0);pending.forEach(function(resolve){resolve()})}}
  document.addEventListener('compositionstart',function(){composing=true},true);
  document.addEventListener('compositionend',function(){composing=false;wake()},true);
  function settled(){return composing||locks?new Promise(function(resolve){waiters.push(resolve)}):Promise.resolve()}
  function parse(html){return new DOMParser().parseFromString(html,'text/html')}
  function identity(node){return node.nodeType===1&&node.id?'#'+node.id:node.nodeType+':'+node.nodeName}
  function pinned(node){return node.nodeType===1&&(node.matches('iframe,audio,video')||node.querySelector('iframe,audio,video'))}
  function morph(live,before,after,undo){
    if(before.isEqualNode(after))return;
    if(live.nodeType!==after.nodeType||live.nodeName!==after.nodeName)throw Error('표시 노드 종류 변경에는 호스트 이행이 필요합니다');
    if(live.nodeType===3){
      if(before.data!==after.data&&live.data===before.data){var text=live.data;undo.push(function(){live.data=text});live.data=after.data}
      return;
    }
    if(live.nodeType!==1)return;
    var attrs=new Set(Array.from(before.attributes).concat(Array.from(after.attributes)).map(function(a){return a.name}));
    attrs.forEach(function(name){
      var old=before.getAttribute(name),next=after.getAttribute(name),actual=live.getAttribute(name);
      if(old===next)return;
      if(name==='id')throw Error('호스트가 소유한 표시 ID를 변경할 수 없습니다');
      // Preserve live state which changed since the old template (visibility, src, value, etc.).
      if(name==='class'){
        var values=new Set((actual||'').split(/\s+/).filter(Boolean));
        (old||'').split(/\s+/).filter(Boolean).forEach(function(v){if(!(next||'').split(/\s+/).includes(v))values.delete(v)});
        (next||'').split(/\s+/).filter(Boolean).forEach(function(v){values.add(v)});next=Array.from(values).join(' ');
      }else if(actual!==old&&!name.startsWith('on'))return;
      undo.push(function(){if(actual===null)live.removeAttribute(name);else live.setAttribute(name,actual)});
      if(next===null)live.removeAttribute(name);else live.setAttribute(name,next);
    });
    if(live.matches('iframe,audio,video,input,textarea'))return;
    var oldChildren=Array.from(before.childNodes),newChildren=Array.from(after.childNodes);
    if(!oldChildren.length&&!newChildren.length)return; // Host-owned results and editor islands.
    var remaining=oldChildren.slice(),pairs=[];
    newChildren.forEach(function(candidate){
      var ix=remaining.findIndex(function(n){return identity(n)===identity(candidate)}),old=ix<0?null:remaining.splice(ix,1)[0];
      var existing=null;
      if(old){
        if(old.nodeType===1&&old.id)existing=Array.from(live.children).find(function(n){return n.id===old.id});
        else{
          var ordinal=oldChildren.filter(function(n){return identity(n)===identity(old)}).indexOf(old);
          existing=Array.from(live.childNodes).filter(function(n){return identity(n)===identity(old)})[ordinal];
        }
        if(!existing&&old.isEqualNode(candidate))return;
        if(!existing)throw Error('호스트가 이동한 표시 영역입니다: '+identity(old));
        morph(existing,old,candidate,undo);
      }else{
        existing=document.importNode(candidate,true);
        if(pinned(existing))throw Error('실행 중 엔진 추가에는 호스트 이행이 필요합니다');
        undo.push(function(){existing.remove()});live.appendChild(existing);
      }
      pairs.push({old:old,node:existing});
    });
    remaining.forEach(function(old){
      var existing=old.nodeType===1&&old.id?Array.from(live.children).find(function(n){return n.id===old.id}):null;
      if(!existing)return;
      if(pinned(existing))throw Error('실행 중 엔진을 표시 갱신으로 제거할 수 없습니다');
      var next=existing.nextSibling;undo.push(function(){live.insertBefore(existing,next&&next.parentNode===live?next:null)});existing.remove();
    });
    // Move only when the source order changed, retaining host-created children.
    var oldOrder=oldChildren.filter(function(n){return n.nodeType===1&&n.id}).map(identity).join('|');
    var newOrder=newChildren.filter(function(n){return n.nodeType===1&&n.id}).map(identity).join('|');
    if(oldOrder!==newOrder){
      var next=null;
      for(var i=pairs.length-1;i>=0;i--){
        var node=pairs[i].node;
        if(node.nextSibling!==next){
          if(pinned(node))throw Error('엔진을 담은 영역의 이동에는 호스트 이행이 필요합니다');
          (function(n,following){undo.push(function(){live.insertBefore(n,following&&following.parentNode===live?following:null)})})(node,node.nextSibling);
          live.insertBefore(node,next);
        }next=node;
      }
    }
  }
  function syntax(candidate){
    // Parse in a sandbox without native bridges, network permissions or access to host state.
    return new Promise(function(resolve,reject){
      var frame=document.createElement('iframe'),token='display-'+Math.random().toString(36).slice(2),timer;
      frame.hidden=true;frame.sandbox='allow-scripts';
      function finish(error){clearTimeout(timer);window.removeEventListener('message',receive);frame.remove();error?reject(Error(error)):resolve()}
      function receive(event){if(event.source===frame.contentWindow&&event.data?.token===token)finish(event.data.error)}
      window.addEventListener('message',receive);
      timer=setTimeout(function(){finish('표시 후보 구문 검사가 응답하지 않습니다')},5000);
      var nonce=JSON.stringify(token),code=candidate.code.replace(/<\/script/gi,'<\\/script');
      frame.srcdoc='<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'">'+
        '<script>window.__ui={text:function(){return ""},source:function(c,v){return v}};window.onerror=function(m){parent.postMessage({token:'+nonce+',error:String(m)},"*")};<\/script>'+
        '<script>'+code+'<\/script><script>parent.postMessage({token:'+nonce+'},"*")<\/script>';
      document.body.appendChild(frame);
    });
  }
  function installCode(code){var script=document.createElement('script');script.textContent=code;document.head.appendChild(script);script.remove()}
  function validate(candidate){
    if(!current||candidate.format!=='indiebiz-display-1'||candidate.surface!==current.surface||candidate.host!==current.host||candidate.state!==current.state)throw Error('이 화면에는 실행부 업데이트가 필요합니다');
    if(JSON.stringify(candidate.names)!==JSON.stringify(current.names))throw Error('표시 함수 계약이 다릅니다');
    if(typeof candidate.code!=='string'||typeof candidate.template!=='string'||!Array.isArray(candidate.styles)||candidate.styles.length!==current.styles.length)throw Error('표시 판본 형식 오류');
    var doc=parse(candidate.template),baseline=parse(current.template);protectedIds.concat(current.requiredIds||[]).forEach(function(id){if(baseline.getElementById(id)&&!doc.getElementById(id))throw Error('상태 소유 영역 누락: '+id)});
    return doc;
  }
  async function apply(candidate){
    if(busy)throw Error('다른 화면 갱신이 진행 중입니다');
    busy=true;var frameApplied=false;
    try{
      var next=validate(candidate);await syntax(candidate);await settled();
      if(candidate.frame){await root.IndieFrame.apply(candidate.frame);frameApplied=true;await settled();}
      // Capture latest state after preparation. No asynchronous gap during commit or rollback.
      var previous=current,old=parse(current.template),undo=[],functions={};
      current.names.forEach(function(name){functions[name]=root[name]});
      var focus=document.activeElement,selection=focus&&typeof focus.selectionStart==='number'?[focus.selectionStart,focus.selectionEnd,focus.selectionDirection]:null;
      var scroll=Array.from(document.querySelectorAll('[id]')).map(function(n){return [n,n.scrollTop,n.scrollLeft]});
      try{
        if(root.__ui&&candidate.messages)undo.push(root.__ui.installMessages(candidate.messages));
        installCode(candidate.code);
        candidate.names.forEach(function(name){if(typeof root[name]!=='function')throw Error('표시 함수 누락: '+name)});
        morph(document.body,old.body,next.body,undo);
        var styles=Array.from(document.querySelectorAll('style[data-indie-display]'));
        if(styles.length!==candidate.styles.length)throw Error('표시 스타일 계약 불일치');
        styles.forEach(function(style,i){var text=style.textContent;undo.push(function(){style.textContent=text});style.textContent=candidate.styles[i]});
        refresh();previousDisplay=previous;current=candidate;
        root.dispatchEvent(new CustomEvent('indie-display-changed',{detail:{version:current.version}}));
      }catch(error){
        current=previous;current.names.forEach(function(name){root[name]=functions[name]});
        undo.reverse().forEach(function(restore){restore()});refresh();throw error;
      }finally{
        scroll.forEach(function(row){if(row[0].isConnected){row[0].scrollTop=row[1];row[0].scrollLeft=row[2]}});
        if(focus?.isConnected){focus.focus({preventScroll:true});if(selection)focus.setSelectionRange(selection[0],selection[1],selection[2])}
      }
      return {version:current.version};
    }catch(error){if(frameApplied)await root.IndieFrame.rollback(candidate.frame.version);throw error;}finally{busy=false}
  }
  function watch(url){
    if(!/^https?:$/.test(location.protocol))return;
    var button=document.createElement('button'),offer=null,installing=false;
    button.id='surfaceUpdate';button.hidden=true;button.textContent='새 화면 있음';
    button.style.cssText='position:fixed;right:12px;bottom:12px;z-index:10000;padding:8px 12px;border-radius:8px';
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){document.body.appendChild(button)});else document.body.appendChild(button);
    async function check(){
      if(installing)return;
      try{var response=await fetch(url+'?display=version',{cache:'no-store',credentials:'same-origin'});if(!response.ok)return;
        var value=await response.json();offer=value.version!==current.version?value:null;
        button.hidden=!offer;button.textContent=offer&&offer.host!==current.host?'앱 업데이트 필요':'새 화면 있음';
      }catch(error){/* Offline keeps the verified display and does not interrupt work. */}
    }
    button.onclick=async function(){
      if(installing||!offer)return;
      if(offer.host!==current.host){button.textContent='실행부가 바뀐 판본입니다. 앱 업데이트 후 적용하세요';return;}
      var selected=offer.version;if(!root.confirm('새 화면을 적용할까요? 작성 중인 내용과 진행 중 작업은 유지됩니다.'))return;
      installing=true;button.disabled=true;
      try{var response=await fetch(url+'?display=module',{cache:'no-store',credentials:'same-origin'});if(!response.ok)throw Error('화면을 내려받지 못했습니다');
        var value=await response.json();if(value.version!==selected)throw Error('선택한 판본이 변경됐습니다. 다시 확인하세요');
        await apply(value);offer=null;button.hidden=true;
      }catch(error){button.textContent='화면 유지 · '+error.message;}
      finally{installing=false;button.disabled=false;}
    };
    setTimeout(check,15000);setInterval(check,60000);
  }
  root.IndieDisplay={
    start:function(value,render){refresh=render||function(){};if(current)throw Error('표시 호스트는 한 번만 시작합니다');current=value;document.querySelectorAll('style').forEach(function(style){style.setAttribute('data-indie-display','')})},
    apply:apply,
    watch:watch,
    rollback:function(version){if(!previousDisplay||current.version!==version)throw Error('복구할 표시 판본이 다릅니다');return apply(previousDisplay)},
    current:function(){return current&&{version:current.version,host:current.host,surface:current.surface}},
    hold:function(){locks++;var released=false;return function(){if(!released){released=true;locks--;wake()}}}
  };
})(window);
