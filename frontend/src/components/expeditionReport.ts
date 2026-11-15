import type { GlobalRoute } from '../types'
import { strategicRoute } from './routeAssessment'

const escape=(v:unknown)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
const number=(n:number)=>n.toLocaleString('en-US',{maximumFractionDigits:2})
export function reportHtml(route:GlobalRoute){
  const m=route.metrics!,g=route.route!.geometry
  const coords=g.type==='LineString'?g.coordinates:g.type==='Point'?[g.coordinates]:[]
  const paths:string[]=[]
  coords.forEach((p,i)=>{
    const x=(p[0]+180)/360*900,y=(90-p[1])/180*450
    if(!i||Math.abs(p[0]-coords[i-1][0])>180)paths.push(`M${x},${y}`)
    else paths[paths.length-1]+=` L${x},${y}`
  })
  const profile=route.profile??[]
  const low=profile.reduce((v,p)=>Math.min(v,p.elevation_m),m.min_elevation_m)
  const high=profile.reduce((v,p)=>Math.max(v,p.elevation_m),m.max_elevation_m)
  const line=profile.map(p=>`${20+p.distance_m/Math.max(1,m.distance_m)*860},${150-(p.elevation_m-low)/Math.max(1,high-low)*130}`).join(' ')
  return `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mars Explorer — Route report</title><style>
body{font:15px/1.7 system-ui,sans-serif;color:#172733;background:#edf1f3;margin:0}main{max-width:1050px;margin:30px auto;padding:40px;background:white}h1{font-size:36px;line-height:1.2}h2{font-size:22px;border-bottom:1px solid #ccd4da;padding-bottom:10px}small{color:#4b5a66}button{padding:13px 20px;background:#1d3944;color:white;border:0;border-radius:6px;cursor:pointer}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.stats strong{font-size:21px;display:block}svg{width:100%;height:auto;border:1px solid #c7d0d6}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:8px;border:1px solid #ced8df;text-align:left}a{color:#22576b;overflow-wrap:anywhere}@media(max-width:700px){main{padding:20px;margin:0}.stats{grid-template-columns:1fr 1fr}}@media print{body{background:white}main{margin:0;padding:0}button{display:none}h2,svg{break-inside:avoid}a{color:inherit}}
</style><main><button onclick="window.print()">Print / Save as PDF</button><p>MARS EXPLORER / ROUTE REPORT</p><h1>Route report</h1><small>${escape(new Date().toLocaleString('en-US'))} · ${escape(route.data_quality?.product||route.dataset)}</small>
<div class="stats">${[['Distance',number(m.distance_m/1000)+' km'],['Ascent',number(m.ascent_m)+' m'],['Descent',number(m.descent_m)+' m'],['Maximum slope',number(m.max_surface_slope_deg??m.max_grade_deg)+'°']].map(([a,b])=>`<div>${a}<strong>${b}</strong></div>`).join('')}</div>
<h2>Route overview</h2><svg viewBox="0 0 900 450" role="img" aria-label="Route on a Mars coordinate grid"><rect width="900" height="450" fill="#10212d"/>${[-60,-30,0,30,60].map(lat=>`<path d="M0 ${(90-lat)/180*450}H900" stroke="#344956"/>`).join('')}${[-120,-60,0,60,120].map(lon=>`<path d="M${(lon+180)/360*900} 0V450" stroke="#344956"/>`).join('')}<path d="${paths.join(' ')}" fill="none" stroke="${strategicRoute(route)?'#f0b180':'#a2ebcf'}" ${strategicRoute(route)?'stroke-dasharray="8 7"':''} stroke-width="3"/></svg>
<h2>Elevation profile</h2><svg viewBox="0 0 900 180" role="img" aria-label="Route elevation profile"><polyline points="${line}" fill="none" stroke="#b87947" stroke-width="2"/></svg><p>${number(m.min_elevation_m)} … ${number(m.max_elevation_m)} m · ${escape(route.data_quality?.vertical_datum)}</p>
<h2>Route legs</h2><table><thead><tr><th>Leg</th><th>Start [lon, lat]</th><th>End [lon, lat]</th><th>Distance, km</th></tr></thead><tbody>${(route.legs||[]).map(l=>`<tr><td>${l.index+1}</td><td>${escape(l.start.join(', '))}</td><td>${escape(l.end.join(', '))}</td><td>${number(l.distance_m/1000)}</td></tr>`).join('')}</tbody></table>
<h2>Geology</h2><ul>${(route.geological_units||[]).map(u=>`<li><b>${escape(u.unit)}</b> — ${escape(u.description)}</li>`).join('')||'<li>No geological units recorded.</li>'}</ul>
<h2>Data</h2><table><tbody><tr><th>DEM spacing</th><td>${number(route.data_quality?.equatorial_spacing_m||route.terrain_validation?.spacing_m||0)} m</td></tr><tr><th>Cells</th><td>${m.cells}</td></tr><tr><th>Interpolated cells</th><td>${m.interpolated_cells}</td></tr><tr><th>Endpoint offsets</th><td>${m.snap_offsets_m.map(number).join(' / ')} m</td></tr></tbody></table>
<h2>Sources</h2><p><a href="${escape(route.data_quality?.source)}">${escape(route.data_quality?.source)}</a><br><a href="https://doi.org/10.3133/sim3292">USGS Geologic Map of Mars — SIM 3292</a></p></main></html>`
}
export function downloadReport(result:GlobalRoute){
  const url=URL.createObjectURL(new Blob([reportHtml(result)],{type:'text/html;charset=utf-8'}))
  const a=document.createElement('a');a.href=url;a.download='mars-expedition-report.html';a.click();URL.revokeObjectURL(url)
}
