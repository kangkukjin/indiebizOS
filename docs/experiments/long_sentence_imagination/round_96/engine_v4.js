/* Directly authored approximation. No original StarCraft execution was observed. */
(function (root) {
  'use strict';
  const RULES = {hp:40, damage:6, cooldown:15, range:128, sight:224,
    radius:6, speed:2, cell:16, ticksPerSecond:24};
  const clone = x => JSON.parse(JSON.stringify(x));
  const distance = (a,b) => Math.hypot(a.x-b.x,a.y-b.y);
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  function create(scenario) {
    const s=clone(scenario), r=RULES;
    if (!finite(s.width)||!finite(s.height)||s.width<32||s.height<32||s.width>2048||s.height>2048)
      throw Error('invalid map size');
    if (!Array.isArray(s.units)||s.units.length>200||!Array.isArray(s.walls)||!Array.isArray(s.commands))
      throw Error('invalid arrays');
    const ids=new Set();
    for (const w of s.walls) if (![w.x,w.y,w.w,w.h].every(finite)||w.w<=0||w.h<=0) throw Error('invalid wall');
    const units=s.units.map(u=>{
      if (typeof u.id!=='string'||ids.has(u.id)||!finite(u.x)||!finite(u.y)||![0,1].includes(u.team)) throw Error('invalid unit');
      ids.add(u.id);
      const hp=u.hp===undefined?r.hp:u.hp;
      if (!finite(hp)||hp<0||hp>r.hp) throw Error('invalid hp');
      return {...u,hp,alive:hp>0,cooldown:0,order:{kind:'stop'}};
    }).sort((a,b)=>a.id.localeCompare(b.id));
    const blocked=(x,y)=>x<r.radius||y<r.radius||x>s.width-r.radius||y>s.height-r.radius||
      s.walls.some(w=>x>w.x-r.radius&&x<w.x+w.w+r.radius&&y>w.y-r.radius&&y<w.y+w.h+r.radius);
    for (const u of units) if (u.alive && blocked(u.x,u.y)) throw Error('unit inside wall/bounds');
    for(let i=0;i<units.length;i++) for(let j=i+1;j<units.length;j++)
      if(units[i].alive&&units[j].alive&&distance(units[i],units[j])<r.radius*2-1e-6) throw Error('units overlap');
    const validateCommand=c=>{
      if(!Number.isInteger(c.tick)||c.tick<0||!Array.isArray(c.ids)||c.ids.some(id=>!ids.has(id))||
        !['move','attack','attackMove','stop'].includes(c.kind)) throw Error('invalid command');
      if(['move','attackMove'].includes(c.kind)&&(!finite(c.x)||!finite(c.y))) throw Error('invalid destination');
      if(c.kind==='attack'&&!ids.has(c.targetId)) throw Error('invalid target');
    };
    s.commands.forEach(validateCommand);
    const cols=Math.ceil(s.width/r.cell), rows=Math.ceil(s.height/r.cell), fields=new Map();
    const center=i=>({x:(i%cols)*r.cell+r.cell/2,y:Math.floor(i/cols)*r.cell+r.cell/2});
    const index=p=>Math.max(0,Math.min(rows-1,Math.floor(p.y/r.cell)))*cols+Math.max(0,Math.min(cols-1,Math.floor(p.x/r.cell)));
    const passable=Array.from({length:cols*rows},(_,i)=>{const p=center(i);return !blocked(p.x,p.y)});
    function neighbors(i){
      const x=i%cols,y=Math.floor(i/cols),out=[];
      for(const [dx,dy] of [[1,0],[0,1],[-1,0],[0,-1]]){
        const nx=x+dx,ny=y+dy;
        if(nx>=0&&ny>=0&&nx<cols&&ny<rows&&passable[ny*cols+nx]) out.push(ny*cols+nx);
      } return out;
    }
    function field(goal){
      let k=index(goal);
      if(!passable[k]){
        let best=Infinity;
        for(let i=0;i<passable.length;i++) if(passable[i]){const d=distance(center(i),goal);if(d<best){best=d;k=i}}
      }
      if(fields.has(k))return fields.get(k);
      const d=new Int32Array(cols*rows).fill(-1),q=[k];d[k]=0;
      for(let p=0;p<q.length;p++)for(const j of neighbors(q[p]))if(d[j]<0){d[j]=d[q[p]]+1;q.push(j)}
      if(fields.size>256)fields.clear();fields.set(k,d);return d;
    }
    function canMove(u,x,y){return !blocked(x,y)&&units.every(v=>v===u||!v.alive||Math.hypot(x-v.x,y-v.y)>=r.radius*2-1e-7)}
    function lineClear(a,b){
      const n=Math.max(1,Math.ceil(distance(a,b)/4));
      for(let i=1;i<n;i++){const x=a.x+(b.x-a.x)*i/n,y=a.y+(b.y-a.y)*i/n;
        if(s.walls.some(w=>x>w.x&&x<w.x+w.w&&y>w.y&&y<w.y+w.h))return false;
      }return true;
    }
    function advance(u,goal){
      if(distance(u,goal)<=r.speed){if(canMove(u,goal.x,goal.y)){u.x=goal.x;u.y=goal.y}return}
      let d=field(goal);const at=index(u);
      u.navTicks=(u.navTicks||0)+1;
      if(u.detourField&&u.navTicks<u.detourUntil)d=u.detourField;
      if((u.stuck||0)>=5&&(!u.detourUntil||u.navTicks>=u.detourUntil)){
        const free=passable.map((ok,i)=>{const p=center(i);return ok&&units.every(v=>v===u||!v.alive||distance(p,v)>=r.radius*2+1)});
        free[at]=true;
        let goalIndex=-1,best=Infinity;
        for(let i=0;i<free.length;i++)if(free[i]){const dd=distance(center(i),goal);if(dd<best){best=dd;goalIndex=i}}
        if(goalIndex>=0){
          const dynamic=new Int32Array(cols*rows).fill(-1),queue=[goalIndex];dynamic[goalIndex]=0;
          for(let k=0;k<queue.length;k++)for(const j of neighbors(queue[k]))if(free[j]&&dynamic[j]<0){dynamic[j]=dynamic[queue[k]]+1;queue.push(j)}
          if(dynamic[at]>=0){d=dynamic;u.detourField=dynamic;}u.detourUntil=u.navTicks+40;
        }
      }
      if(d[at]<0)return;
      const choices=neighbors(at).filter(i=>d[i]>=0&&d[i]<d[at]).sort((a,b)=>d[a]-d[b]||distance(center(a),goal)-distance(center(b),goal));
      const aims=d[at]===0?[goal]:choices.map(center);
      for(const aim of aims){
        const len=distance(u,aim),amount=Math.min(r.speed,len);if(!len)continue;
        const dx=(aim.x-u.x)/len*amount,dy=(aim.y-u.y)/len*amount;
        for(const [x,y] of [[u.x+dx,u.y+dy],[u.x+dx,u.y],[u.x,u.y+dy]])
          if((Math.abs(x-u.x)+Math.abs(y-u.y)>1e-8)&&canMove(u,x,y)){u.x=x;u.y=y;u.stuck=Math.max(0,(u.stuck||0)-1);return}
      }
      u.stuck=(u.stuck||0)+1;
    }
    let tick=0;const events=[];
    const state=()=>units.map(({id,team,x,y,hp,alive})=>({id,team,x:+x.toFixed(6),y:+y.toFixed(6),hp,alive}));
    function command(c){validateCommand(c);s.commands.push(clone(c))}
    function step(){
      for(const c of s.commands.filter(c=>c.tick===tick)){
        const group=units.filter(u=>u.alive&&c.ids.includes(u.id));
        group.forEach((u,i)=>{
          let x=c.x,y=c.y;
          if(group.length>1&&['move','attackMove'].includes(c.kind)){
            const n=Math.ceil(Math.sqrt(group.length));x+=(i%n-(n-1)/2)*16;y+=(Math.floor(i/n)-(n-1)/2)*16;
            x=Math.max(r.radius,Math.min(s.width-r.radius,x));y=Math.max(r.radius,Math.min(s.height-r.radius,y));
          }
          u.order={...c,x,y};u.detourField=null;u.detourUntil=0;u.stuck=0;
        });
      }
      const alive=units.filter(u=>u.alive), shots=[];
      // Rotating, deterministic movement priority is an explicit approximation.
      for(let k=0;k<alive.length;k++){
        const u=alive[(k+tick)%alive.length],o=u.order;
        if(u.cooldown>0)u.cooldown--;
        let target=null;
        if(o.kind==='attack')target=units.find(v=>v.id===o.targetId&&v.alive&&v.team!==u.team)||null;
        else if(o.kind!=='move')target=alive.filter(v=>v.team!==u.team&&distance(u,v)<=r.sight&&lineClear(u,v))
          .sort((a,b)=>distance(u,a)-distance(u,b)||a.id.localeCompare(b.id))[0]||null;
        if(target&&distance(u,target)<=r.range&&lineClear(u,target)){
          if(u.cooldown===0){shots.push([u,target]);u.cooldown=r.cooldown;}
        }else if(target&&['attack','attackMove'].includes(o.kind))advance(u,target);
        else if(['move','attackMove'].includes(o.kind))advance(u,o);
      }
      for(const [u,v] of shots){
        events.push({type:'fire',tick,actor:u.id,target:v.id});
        if(v.hp>0){const damage=Math.min(v.hp,r.damage);v.hp-=damage;events.push({type:'damage',tick,actor:u.id,target:v.id,damage,hp:v.hp});}
      }
      for(const u of alive)if(u.hp===0){u.alive=false;events.push({type:'death',tick,target:u.id});}
      tick++;return state();
    }
    return {step,state,command,events,get tick(){return tick},scenario:s};
  }
  function simulate(s){
    if(!Number.isInteger(s.ticks)||s.ticks<0||s.ticks>4000)throw Error('invalid ticks');
    const world=create(s),frames=[];
    for(let i=0;i<s.ticks;i++)frames.push({tick:i,units:world.step()});
    return {final:world.state(),events:world.events,frames};
  }
  const api={create,simulate,RULES};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.RTS=api;
})(typeof window!=='undefined'?window:globalThis);
