/* Same external scenarios; differences in assumed physics are recorded, not called original errors. */
const fs=require('fs'),crypto=require('crypto'),engine=require(process.argv[2]);
const cases=JSON.parse(fs.readFileSync(process.argv[3],'utf8')),radius=engine.RULES.radius,results=[];
for(const c of cases){
 const s=c.scenario,began=Date.now();
 try{
  const a=engine.simulate(s),b=engine.simulate(s);let collisions=0,wallContacts=0,invalid=0,deadActions=0;
  const dead=new Map();
  for(const f of a.frames){const us=Array.isArray(f)?f:f.units;
   for(const u of us){if(!Number.isFinite(u.x)||!Number.isFinite(u.y)||!Number.isFinite(u.hp)||u.hp<0||u.hp>40)invalid++;
    if(!u.alive&&!dead.has(u.id))dead.set(u.id,f.tick);
    if(u.alive)for(const w of s.walls){const x=Math.max(w.x,Math.min(w.x+w.w,u.x)),y=Math.max(w.y,Math.min(w.y+w.h,u.y));
     if((u.x-x)**2+(u.y-y)**2<(radius-1e-5)**2)wallContacts++;
    }
   }
   for(let i=0;i<us.length;i++)for(let j=i+1;j<us.length;j++)if(us[i].alive&&us[j].alive&&
     (us[i].x-us[j].x)**2+(us[i].y-us[j].y)**2<(2*radius-1e-5)**2)collisions++;
  }
  const fires=a.events.filter(e=>['fire','shot','attack'].includes(e.type));
  for(const e of fires){const id=e.actor??e.attacker??e.unitId??e.source;if(dead.has(id)&&e.tick>dead.get(id))deadActions++;}
  results.push({name:s.name,kind:c.kind,executed:true,deterministic:JSON.stringify(a)===JSON.stringify(b),
    collisions,wallContacts,invalid,deadActions,shots:fires.length,events:a.events.length,
    survivors:a.final.filter(u=>u.alive).length,passed_right:a.final.filter(u=>u.x>520).length,total:a.final.length,
    final:a.final,trace_sha256:crypto.createHash('sha256').update(JSON.stringify(a)).digest('hex'),wall_ms:Date.now()-began});
 }catch(e){results.push({name:s.name,kind:c.kind,executed:false,error:String(e),wall_ms:Date.now()-began});}
}
const value={engine:process.argv[2],radius,original_equivalence_verified:false,results};
fs.writeFileSync(process.argv[4],JSON.stringify(value,null,2));
console.log(JSON.stringify(results.map(({final,...r})=>r)));
