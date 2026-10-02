/* Official ONLYOFFICE plugin API. Only fixed, data-only editor commands. */
(function () {
  'use strict';
  var params = new URLSearchParams(location.search);
  var channel = params.get('channel'), origin = (params.get('ib_parent') || '').split('?')[0];
  var targetOrigin = origin === 'null' ? '*' : origin;
  function reply(id, result) { window.top.postMessage({type:'indiebiz-document',channel:channel,id:id,result:result},targetOrigin); }
  window.Asc.plugin.init = function () {
    reply('ready',{ready:true});
    window.addEventListener('message', function (event) {
      var message = event.data;

      if (event.source !== window.top || event.origin !== origin || !message || message.type !== 'indiebiz-document-command' || message.channel !== channel) return;
      if (!['select','apply','discard'].includes(message.op)) return;
      var data = message.args || {};
      if (typeof data.bookmark !== 'string' || !/^ib_[a-f0-9]{24}$/.test(data.bookmark)) return;
      Asc.scope = Asc.scope || {};
      Asc.scope.documentAction = {op:message.op, bookmark:data.bookmark, selected:data.selected, replacement:data.replacement, track:data.track !== false};
      window.Asc.plugin.callCommand(function () {
        try {
        var args=Asc.scope.documentAction, doc=Api.GetDocument();
        if(args.op==='select') {
          var range=doc.GetRangeBySelect();
          if(!range) return {error:'문서에서 수정할 문구를 선택하세요'};
          var text=range.GetText();
          if(!text || text.length>20000) return {error:'선택은 1~20000자여야 합니다'};
          if(!range.AddBookmark(args.bookmark)) return {error:'선택 위치를 고정하지 못했습니다'};
          return {text:text,bookmark:args.bookmark};
        }
        var bookmark=doc.GetBookmark(args.bookmark);
        if(!bookmark) return {error:'고정한 선택이 없어졌습니다. 다시 선택하세요'};
        if(args.op==='discard') { bookmark.Delete(); return {discarded:true}; }
        if(bookmark.GetText()!==args.selected) return {error:'선택 내용이 바뀌었습니다. 제안을 다시 만드세요'};
        if(typeof args.replacement!=='string'||args.replacement.length>40000) return {error:'수정 문구 크기를 확인하세요'};
        var tracking=doc.IsTrackRevisions ? doc.IsTrackRevisions() : false;
        if(args.track) doc.SetTrackRevisions(true);
        var applied=bookmark.SetText(args.replacement);
        if(args.track && !tracking) doc.SetTrackRevisions(false);
        return applied ? {applied:true} : {error:'선택 수정에 실패했습니다'};
        } catch (e) { return {error: String(e)}; }
      },false,true,function(result){reply(message.id,result || {error:'편집기가 결과를 반환하지 않았습니다'});});
    });
  };
  window.Asc.plugin.button = function () {};
})();
