/* Generic observations on engine traces. This file supplies measurements, not original-game truth. */
const fs=require('fs'),crypto=require('crypto');
const engine=require(process.argv[2]),s=JSON.parse(fs.readFileSync(0,'utf8'));
const a=engine.simulate(s),b=engine.simulate(s);
let wallContacts=0,overlaps=0,invalidHp=0,deadActions=0;
const dead=new Map();
for(const f of a.frames){const us=f.units;
 for(const u of us){if(!Number.isFinite(u.hp)||u.hp<0||u.hp>40||!Number.isFinite(u.x)||!Number.isFinite(u.y))invalidHp++;
  if(u.alive&&s.walls.some(w=>u.x>w.x-5.999&&u.x<w.x+w.w+5.999&&u.y>w.y-5.999&&u.y<w.y+w.h+5.999))wallContacts++;
  if(!u.alive&&!dead.has(u.id))dead.set(u.id,f.tick);
 }
 for(let i=0;i<us.length;i++)for(let j=i+1;j<us.length;j++)if(us[i].alive&&us[j].alive&&Math.hypot(us[i].x-us[j].x,us[i].y-us[j].y)<11.999)overlaps++;
}
for(const e of a.events)if(e.type==='fire'&&dead.has(e.actor)&&e.tick>dead.get(e.actor))deadActions++;
process.stdout.write(JSON.stringify({name:s.name,deterministic:JSON.stringify(a)===JSON.stringify(b),
 wallContacts,overlaps,invalidHp,deadActions,frames:a.frames.length,events:a.events.length,
 shots:a.events.filter(e=>e.type==='fire').length,final:a.final,
 trace_sha256:crypto.createHash('sha256').update(JSON.stringify(a)).digest('hex')}));
