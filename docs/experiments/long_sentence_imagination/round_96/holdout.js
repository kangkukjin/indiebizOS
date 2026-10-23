/* Independent checks of public API behavior; no original-engine equality claim. */
const fs=require('fs'),engine=require(process.argv[2]),out=process.argv[3];
const checks=[];
function check(name,passed,detail=null){checks.push({name,passed:!!passed,detail});}
function base(){return {width:960,height:544,walls:[],units:[{id:'a',team:0,x:80,y:104}],commands:[],ticks:100,seed:521};}
function attempt(name,fn){try{fn()}catch(e){check(name,false,String(e));}}
function frameUnits(f){return Array.isArray(f)?f:(f.units||f.state);}
function assertRejected(name,edit){const s=base();edit(s);let rejected=false;try{engine.simulate(s)}catch(e){rejected=true;}check(name,rejected);}
attempt('stop_exact',()=>{
 const s=base();s.commands=[{tick:0,ids:['a'],kind:'move',x:700,y:104},{tick:20,ids:['a'],kind:'stop'}];
 const r=engine.simulate(s),a=frameUnits(r.frames[20]).find(u=>u.id==='a');
 check('stop_exact',r.frames.slice(20).every(f=>{const b=frameUnits(f).find(u=>u.id==='a');return b.x===a.x&&b.y===a.y}));
 check('move_progress_before_stop',a.x>80);
});
attempt('explicit_target',()=>{
 const s=base();s.units.push({id:'b',team:1,x:180,y:104},{id:'c',team:1,x:140,y:104});s.ticks=1;
 s.commands=[{tick:0,ids:['a'],kind:'attack',targetId:'b'}];
 const r=engine.simulate(s);check('explicit_target',r.final.find(u=>u.id==='b').hp<40&&r.final.find(u=>u.id==='c').hp===40);
});
attempt('move_does_not_fire',()=>{
 const s=base();s.units.push({id:'b',team:1,x:160,y:104});s.ticks=10;
 s.commands=[{tick:0,ids:['a'],kind:'move',x:400,y:104}];
 check('move_does_not_fire',engine.simulate(s).final.find(u=>u.id==='b').hp===40);
});
attempt('range_boundary',()=>{
 const s=base();s.units.push({id:'b',team:1,x:500,y:104});s.ticks=50;
 const r=engine.simulate(s);check('distant_idle_no_damage',r.final.every(u=>u.hp===40));
});
attempt('deterministic',()=>{const s=base();check('deterministic',JSON.stringify(engine.simulate(s))===JSON.stringify(engine.simulate(s)));});
assertRejected('duplicate_ids',s=>s.units.push({...s.units[0],x:150}));
assertRejected('nan_position',s=>s.units[0].x=NaN);
assertRejected('negative_ticks',s=>s.ticks=-1);
assertRejected('unknown_command_unit',s=>s.commands=[{tick:0,ids:['missing'],kind:'stop'}]);
assertRejected('overlapping_start',s=>s.units.push({...s.units[0],id:'b'}));
assertRejected('unit_in_wall',s=>s.walls=[{x:70,y:90,w:30,h:30}]);
const result={engine:process.argv[2],passed:checks.filter(x=>x.passed).length,total:checks.length,checks,
 original_equivalence_verified:false};
fs.writeFileSync(out,JSON.stringify(result,null,2));console.log(JSON.stringify(result));
