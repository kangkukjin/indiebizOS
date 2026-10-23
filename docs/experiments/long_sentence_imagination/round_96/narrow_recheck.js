/* Recheck the four reported remaining failures plus a neighboring success, independently. */
const fs=require('fs'),engine=require(process.argv[2]),results=[];
for(const [y,n,gap] of [[90,35,16],[260,35,16],[470,12,16],[470,35,16],[90,35,18]]){
 const rows=Math.ceil(n/5),y0=Math.min(540-(rows-1)*22,Math.max(20,y+gap/2-(rows-1)*11));
 const units=Array.from({length:n},(_,i)=>({id:'R'+(i+1),team:2,x:800+(i%5)*22,y:y0+Math.floor(i/5)*22}));
 const s={width:960,height:560,walls:[{x:620,y:0,w:60,h:y},{x:620,y:y+gap,w:60,h:560-y-gap}],
   units,commands:[{tick:0,ids:units.map(u=>u.id),kind:'move',x:470,y:280}],ticks:15000,seed:11};
 const r=engine.simulate(s);let overlap=0,wall=0;
 for(const f of r.frames){
  for(const u of f.units){for(const w of s.walls){const dx=u.x-Math.max(w.x,Math.min(w.x+w.w,u.x)),dy=u.y-Math.max(w.y,Math.min(w.y+w.h,u.y));if(dx*dx+dy*dy<64-1e-5)wall++;}}
  for(let i=0;i<f.units.length;i++)for(let j=i+1;j<f.units.length;j++){const a=f.units[i],b=f.units[j];if((a.x-b.x)**2+(a.y-b.y)**2<256-1e-5)overlap++;}
 }
 results.push({wall_x:620,wall_width:60,gap_y:y,gap_width:gap,units:n,ticks:15000,
   crossed:r.final.filter(u=>u.x<612).length,wall_contacts:wall,unit_overlaps:overlap});
}
fs.writeFileSync(process.argv[3],JSON.stringify(results,null,2));console.log(JSON.stringify(results));
