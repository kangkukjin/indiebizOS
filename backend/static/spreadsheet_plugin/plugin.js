/* Official ONLYOFFICE plugin. Commands are fixed; payloads are data, never code. */
(function () {
  'use strict';
  var query=new URLSearchParams(location.search);
  var channel=query.get('channel'), origin=(query.get('ib_parent')||'').split('?')[0];
  var target=origin==='null'?'*':origin;
  var busy=false;
  function reply(id,result) { window.top.postMessage({type:'indiebiz-sheet',channel:channel,id:id,result:result},target); }
  Asc.plugin.init=function () {
    reply('ready',{ready:true});
    window.addEventListener('message',function(event){
      var message=event.data;
      if(event.source!==window.top||event.origin!==origin||!message||message.type!=='indiebiz-sheet-command'||message.channel!==channel) return;
      if(!['state','calculate','apply'].includes(message.op)) return;
      if(busy) {reply(message.id,{error:'다른 편집 작업이 진행 중입니다'});return;}
      busy=true;
      Asc.scope=Asc.scope||{};
      Asc.scope.sheetCommand={op:message.op,args:message.args||{}};
      Asc.plugin.callCommand(function(){
        function state() {
          var sheets=Api.GetSheets(), result=[], count=0;
          for(var i=0;i<sheets.length;i++) {
            var used=sheets[i].GetUsedRange(), address=used.GetAddress();
            var match=address.match(/\$?([A-Z]+)\$?([0-9]+)(?::\$?([A-Z]+)\$?([0-9]+))?$/);
            if(!match) throw new Error('사용 범위를 확인하지 못했습니다');
            function column(s){var n=0;for(var j=0;j<s.length;j++)n=n*26+s.charCodeAt(j)-64;return n;}
            count+=(column(match[3]||match[1])-column(match[1])+1)*(Number(match[4]||match[2])-Number(match[2])+1);
            if(count>20000) throw new Error('현재 AI 스냅샷 상한은 20,000셀입니다. 직접 편집과 파일 저장은 계속 가능합니다');
            result.push({name:sheets[i].GetName(),address:address,values:used.GetValue(),formulas:used.GetFormula(),format:used.GetNumberFormat()});
          }
          return JSON.stringify(result);
        }
        try {
          var command=Asc.scope.sheetCommand, args=command.args;
          var differences=[];
          if(command.op==='calculate') {
            // 9.3.1 returns void. Its logger reports cached/recomputed differences.
            Api.RecalculateAllFormulas(function(change){differences.push(change);});
            Api.RefreshAllPivots();
          }
          var before=state();
          if(command.op!=='apply') return {engine_state:before,calculation:command.op==='calculate'&&differences.length===0?'fresh':'stale',calculation_differences:differences.length};
          if(typeof args.engine_state!=='string'||args.engine_state!==before) return {error:'제안 이후 셀·시트 구조가 바뀌었습니다. 스냅샷을 다시 만드세요'};
          var sheet=Api.GetSheet(args.sheet_name);
          if(!sheet||!/^([A-Z]{1,3}[1-9][0-9]*)(:[A-Z]{1,3}[1-9][0-9]*)?$/.test(args.range)) return {error:'대상 시트 또는 범위가 없습니다'};
          if(!['set_values','set_formulas'].includes(args.kind)||!Array.isArray(args.values)) return {error:'지원하지 않는 변경입니다'};
          var range=sheet.GetRange(args.range), values=args.values;
          var old=[], rows=values.length, cols=rows?values[0].length:0;
          if(!rows||!cols||rows*cols>10000) return {error:'수정 범위 상한을 확인하세요'};
          for(var r=0;r<rows;r++) {
            if(!Array.isArray(values[r])||values[r].length!==cols) return {error:'수정 값의 행열 수가 다릅니다'};
            old[r]=[];
            for(var c=0;c<cols;c++) {
              var cell=range.GetCells(r+1,c+1), value=values[r][c];
              if(value!==null&&!['string','number','boolean'].includes(typeof value)) return {error:'허용되지 않는 셀 값입니다'};
              if(typeof value==='number'&&!Number.isFinite(value)) return {error:'유한한 숫자만 입력하세요'};
              if(args.kind==='set_formulas'&&(typeof value!=='string'||value[0]!=='='||/\[[^\]]+\][A-Za-z0-9 _.']*!|https?:|WEBSERVICE|IMAGE\s*\(|RTD\s*\(|\|/i.test(value))) return {error:'외부 접근 또는 올바르지 않은 수식입니다'};
              old[r][c]={value:cell.GetValue(),formula:cell.GetFormula(),format:cell.GetNumberFormat()};
            }
          }
          function set(cell,value,formula) {
            if(value===null) {cell.SetValue('');return;}
            if(formula) {cell.SetValue(value);return;}
            // Text is explicitly typed; identifiers and formula-looking strings stay text.
            if(typeof value==='string') {cell.SetValue("'"+value);}
            else cell.SetValue(value);
          }
          try {
            for(var rr=0;rr<rows;rr++)for(var cc=0;cc<cols;cc++)set(range.GetCells(rr+1,cc+1),values[rr][cc],args.kind==='set_formulas');
            Api.RecalculateAllFormulas();
            for(var vr=0;vr<rows;vr++)for(var vc=0;vc<cols;vc++){
              var checked=range.GetCells(vr+1,vc+1), expected=values[vr][vc];
              if(args.kind==='set_formulas'){if(checked.GetFormula()!==expected)throw new Error('수식 적용 결과가 요청과 다릅니다');}
              else {var actual=checked.GetValue2();var wanted=expected===null?'':String(expected);
                if(typeof expected==='boolean'){actual=String(actual).toLowerCase();}
                if(String(actual)!==wanted)throw new Error('셀 적용 결과가 요청과 다릅니다');}
            }
            return {applied:true,affected_cells:rows*cols,calculation:'stale'};
          } catch(changeError) {
            try {
              for(var br=0;br<rows;br++)for(var bc=0;bc<cols;bc++) {
                var prior=old[br][bc], target=range.GetCells(br+1,bc+1);
                set(target,typeof prior.formula==='string'&&prior.formula[0]==='='?prior.formula:prior.value,typeof prior.formula==='string'&&prior.formula[0]==='=');
                target.SetNumberFormat(prior.format);
              }
              if(state()!==before) return {error:'수정 실패 후 완전 복원을 확인하지 못했습니다. 원본을 저장하지 말고 복구하세요',recovery_required:true};
              return {error:String(changeError),rolled_back:true};
            } catch(restoreError) {return {error:String(restoreError),recovery_required:true};}
          }
        } catch(error) {return {error:String(error)};}
      },false,message.op!=='state',function(result){busy=false;reply(message.id,result||{error:'편집기 응답이 없습니다'});});
    });
  };
  Asc.plugin.button=function(){};
})();
