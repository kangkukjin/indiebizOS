/* ES5 handoff for legacy Safari. No Promise/fetch/module/DOM replacement of state islands. */
(function(root){
  var current,refresh,composing=false,pending=null;
  function list(nodes){return Array.prototype.slice.call(nodes)}
  function doc(html){var value=document.implementation.createHTMLDocument('');value.documentElement.innerHTML=html;return value}
  function same(a,b){return a.nodeType===b.nodeType&&(a.nodeType===3?a.data===b.data:a.outerHTML===b.outerHTML)}
  function key(n){return n.nodeType===1&&n.id?'#'+n.id:n.nodeType+':'+n.nodeName}
  function morph(live,before,after,undo){
    if(same(before,after))return;
    if(live.nodeType!==after.nodeType||live.nodeName!==after.nodeName)throw Error('호스트 노드 종류 변경');
    if(live.nodeType===3){if(live.data===before.data){var old=live.data;undo.push(function(){live.data=old});live.data=after.data}return}
    if(live.nodeType!==1)return;
    var attrs={};list(before.attributes).concat(list(after.attributes)).forEach(function(a){attrs[a.name]=true});
    Object.keys(attrs).forEach(function(name){var old=before.getAttribute(name),next=after.getAttribute(name),actual=live.getAttribute(name);if(old===next||actual!==old)return;if(name==='id')throw Error('상태 ID 변경');undo.push(function(){if(actual===null)live.removeAttribute(name);else live.setAttribute(name,actual)});if(next===null)live.removeAttribute(name);else live.setAttribute(name,next)});
    if(/^(INPUT|TEXTAREA|IFRAME|AUDIO|VIDEO)$/.test(live.nodeName))return;
    var old=list(before.childNodes),next=list(after.childNodes),liveNodes=list(live.childNodes),used=[],result=[];
    next.forEach(function(n){var index=-1;for(var i=0;i<old.length;i++)if(!used[i]&&key(old[i])===key(n)){index=i;break}
      if(index<0){var added=n.cloneNode(true);undo.push(function(){if(added.parentNode)added.parentNode.removeChild(added)});live.appendChild(added);result.push(added);return}
      used[index]=true;var occurrence=old.slice(0,index).filter(function(x){return key(x)===key(n)}).length;
      var actual=liveNodes.filter(function(x){return key(x)===key(n)})[occurrence];if(!actual){if(same(old[index],n))return;throw Error('상태 영역이 이동했습니다')}
      morph(actual,old[index],n,undo);result.push(actual);
    });
    old.forEach(function(n,index){if(used[index])return;var actual=n.nodeType===1&&n.id?document.getElementById(n.id):null;if(!actual||actual.parentNode!==live)return;var following=actual.nextSibling;undo.push(function(){live.insertBefore(actual,following&&following.parentNode===live?following:null)});live.removeChild(actual)});
    if(old.map(key).join('|')!==next.map(key).join('|')){var following=null;for(var i=result.length-1;i>=0;i--){var n=result[i];if(n.nextSibling!==following){(function(node,oldNext){undo.push(function(){live.insertBefore(node,oldNext&&oldNext.parentNode===live?oldNext:null)})})(n,n.nextSibling);live.insertBefore(n,following)}following=n}}
  }
  function apply(value,done){
    if(pending){done(Error('갱신 진행 중'));return}
    if(composing){pending=function(){pending=null;apply(value,done)};return}
    var undo=[],functions={},old=current;
    try{
      if(value.host!==current.host||value.state!==current.state||value.surface!=='lite'||JSON.stringify(value.names)!==JSON.stringify(current.names))throw Error('실행부가 다른 화면입니다');
      new Function(value.code); // Parse before touching the live page.
      var next=doc(value.template),before=doc(current.template),focus=document.activeElement,selection=focus&&typeof focus.selectionStart==='number'?[focus.selectionStart,focus.selectionEnd]:null;
      current.requiredIds.forEach(function(id){if(document.getElementById(id)&&!next.getElementById(id))throw Error('상태 영역 누락: '+id)});
      var scroll=list(document.querySelectorAll('[id]')).map(function(n){return [n,n.scrollTop,n.scrollLeft]}),top=root.pageYOffset;
      current.names.forEach(function(name){functions[name]=root[name]});
      var script=document.createElement('script');script.text=value.code;document.head.appendChild(script);document.head.removeChild(script);
      value.names.forEach(function(name){if(typeof root[name]!=='function')throw Error('표시 함수 누락')});
      morph(document.body,before.body,next.body,undo);
      var styles=list(document.querySelectorAll('style'));if(styles.length!==value.styles.length)throw Error('스타일 계약 변경');
      styles.forEach(function(style,i){var text=style.textContent;undo.push(function(){style.textContent=text});style.textContent=value.styles[i]});
      refresh();current=value;
    }catch(error){current=old;Object.keys(functions).forEach(function(name){root[name]=functions[name]});undo.reverse().forEach(function(fn){fn()});done(error);return}
    finally{if(scroll)scroll.forEach(function(row){row[0].scrollTop=row[1];row[0].scrollLeft=row[2]});if(top!==undefined)root.scrollTo(0,top);if(focus){focus.focus();if(selection)focus.setSelectionRange(selection[0],selection[1])}}
    done(null);
  }
  document.addEventListener('compositionstart',function(){composing=true},true);
  document.addEventListener('compositionend',function(){composing=false;if(pending)pending()},true);
  root.IndieLite={start:function(value,render){current=value;refresh=render},apply:apply,current:function(){return current},watch:function(api){
    var offer=null,button=document.createElement('button');button.id='surfaceUpdate';button.style.display='none';button.textContent='새 화면 있음';document.body.appendChild(button);
    function check(){api('GET','/launcher/lite?display=version',null,function(status,value){if(status!==200||!value)return;offer=value.version===current.version?null:value;button.style.display=offer?'':'none';button.textContent=offer&&offer.host!==current.host?'앱 업데이트 필요':'새 화면 있음'})}
    button.onclick=function(){if(!offer||!root.confirm('새 화면을 적용할까요? 작성 중인 내용과 작업은 유지됩니다.'))return;var version=offer.version;button.disabled=true;api('GET','/launcher/lite?display=module',null,function(status,value){if(status!==200||!value||value.version!==version){button.disabled=false;button.textContent='판본을 다시 확인하세요';return}apply(value,function(error){button.disabled=false;button.textContent=error?'이전 화면 유지 · '+error.message:'적용 완료';if(!error){offer=null;button.style.display='none'}})})};
    setTimeout(check,15000);setInterval(check,60000);
  }};
})(window);
