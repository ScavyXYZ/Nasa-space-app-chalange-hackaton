import type { GlobalRoute } from '../types'
import { strategicRoute, traversabilityNotice } from './routeAssessment'

const escape=(v:unknown)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
const number=(n:number)=>n.toLocaleString('uk-UA',{maximumFractionDigits:2})
export function reportHtml(route:GlobalRoute){
  const m=route.metrics!,g=route.route!.geometry
  const coords=g.type==='LineString'?g.coordinates:g.type==='Point'?[g.coordinates]:[]
  const paths:string[]=[]
  coords.forEach((p,i)=>{
    const x=(p[0]+180)/360*900,y=(90-p[1])/180*450
    if(!i||Math.abs(p[0]-coords[i-1][0])>180)paths.push(`M${x},${y}`)
    else paths[paths.length-1]+=` L${x},${y}`
  })
  const profile=route.profile!,low=profile.reduce((v,p)=>Math.min(v,p.elevation_m),Infinity),high=profile.reduce((v,p)=>Math.max(v,p.elevation_m),-Infinity)
  const line=profile.map(p=>`${20+p.distance_m/Math.max(1,m.distance_m)*860},${150-(p.elevation_m-low)/Math.max(1,high-low)*130}`).join(' ')
  return `<!doctype html><html lang="uk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mars Explorer — звіт експедиції</title><style>
body{font:15px/1.7 system-ui,sans-serif;color:#172733;background:#edf1f3;margin:0}main{max-width:1050px;margin:30px auto;padding:40px;background:white}h1{font-size:36px;line-height:1.2}h2{font-size:22px;border-bottom:1px solid #ccd4da;padding-bottom:10px}small{color:#4b5a66}button{padding:13px 20px;background:#1d3944;color:white;border:0;border-radius:6px;cursor:pointer}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.stats strong{font-size:21px;display:block}svg{width:100%;height:auto;border:1px solid #c7d0d6}table{border-collapse:collapse;width:100%;font-size:12px}th,td{padding:8px;border:1px solid #ced8df;text-align:left}.notice{padding:15px;background:#fff3dc;border-left:4px solid #c78a35}a{color:#22576b;overflow-wrap:anywhere}@media(max-width:700px){main{padding:20px;margin:0}.stats{grid-template-columns:1fr 1fr}}@media print{body{background:white}main{margin:0;padding:0}button{display:none}h2,svg{break-inside:avoid}a{color:inherit}}
</style><main><button onclick="window.print()">Друк / Зберегти як PDF</button><p>MARS EXPLORER / EXPEDITION BRIEF</p><h1>Марсіанська експедиція</h1><small>${escape(new Date().toLocaleString('uk-UA'))} · ${escape(route.data_quality?.product||route.dataset)} · Mars, NOT WGS84</small>
<p class="notice"><strong>ПРОХІДНІСТЬ НЕ ПІДТВЕРДЖЕНА.</strong> ${escape(traversabilityNotice(route))} Максимальний градієнт нижче — між клітинками DEM, не максимальний локальний схил.</p>
<div class="stats">${[['Відстань',number(m.distance_m/1000)+' км'],['Набір висоти',number(m.ascent_m)+' м'],['Спуск',number(m.descent_m)+' м'],['Макс. градієнт',number(m.max_grade_deg)+'°']].map(([a,b])=>`<div>${a}<strong>${b}</strong></div>`).join('')}</div>
<h2>Огляд маршруту</h2><svg viewBox="0 0 900 450" role="img" aria-label="Схематичний маршрут на координатній сітці Марса"><rect width="900" height="450" fill="#10212d"/>${[-60,-30,0,30,60].map(lat=>`<path d="M0 ${(90-lat)/180*450}H900" stroke="#344956"/>`).join('')}${[-120,-60,0,60,120].map(lon=>`<path d="M${(lon+180)/360*900} 0V450" stroke="#344956"/>`).join('')}<path d="${paths.join(' ')}" fill="none" stroke="${strategicRoute(route)?'#f0b180':'#a2ebcf'}" ${strategicRoute(route)?'stroke-dasharray="8 7"':''} stroke-width="3"/></svg><small>Схематична equirectangular-сітка −180…180°, 90…−90°; не супутникове зображення.</small>
<h2>Профіль висот</h2><svg viewBox="0 0 900 180"><polyline points="${line}" fill="none" stroke="#b87947" stroke-width="2"/></svg><p>Діапазон висот: ${number(m.min_elevation_m)}…${number(m.max_elevation_m)} м. Датум: ${escape(route.data_quality?.vertical_datum)}.</p>
<h2>Перешкоди та детальна перевірка</h2><p>${route.terrain_validation?.entire_route?`Увесь шлях перевірений на числовій MOLA ${number(route.terrain_validation.spacing_m)} м. Максимальний схил поверхні DEM: ${number(m.max_surface_slope_deg??m.max_grade_deg)}°. Кожен перехід і діагональні кути перевірені. Нерозрізнені каталожні борти захищені окремою смугою; однакові висоти не дозволяють перетнути її. Дно кратера не є суцільною перешкодою; для входу/виїзду потрібна детальніша числова DEM.`:route.hazard_policy?.enabled?`Застосовано каталожні обмеження; це не точні полігони бортів.`:'Схили перевірені в обраній локальній DEM; каталог не є суцільною маскою.'}</p><ul>${(route.terrain_checks||[]).map(c=>`<li>MOLA ${number(c.spacing_m)} м · область ${escape(c.id)} · поріг ${number(c.max_grade_deg)}° · інтерпольовано ${number(c.interpolated_fraction*100)}% бінів області. Межі: ${escape(c.bounds.join(', '))}. <a href="${escape(c.source)}">Числова DEM NASA PDS</a>.</li>`).join('')}</ul>
<h2>Етапи експедиції</h2><table><thead><tr><th>Етап</th><th>Початок [lon, lat]</th><th>Кінець [lon, lat]</th><th>Відстань, км</th></tr></thead><tbody>${(route.legs||[]).map(l=>`<tr><td>${l.index+1}</td><td>${escape(l.start.join(', '))}</td><td>${escape(l.end.join(', '))}</td><td>${number(l.distance_m/1000)}</td></tr>`).join('')}</tbody></table>
<h2>Геологічний контекст</h2><p>USGS SIM 3292, 1:20 000 000. Перетини обчислені на вихідних полігонах; карта не описує дрібні перешкоди.</p><ul>${(route.geological_units||[]).map(u=>`<li><b>${escape(u.unit)}</b> — ${escape(u.description)}</li>`).join('')||'<li>Геологічні одиниці не визначені.</li>'}</ul>
<h2>Якість даних і обмеження</h2><ul><li>Крок моделі: ${number(route.data_quality?.equatorial_spacing_m||0)} м; роздільність не дорівнює точності.</li><li>Абсолютна висота не блокує плавний підйом; враховується градієнт, довжина по схилу та якість DEM. Ґрунт, зчеплення й каміння без вимірювань невідомі.</li><li>Клітинок: ${m.cells}; з офіційною інтерполяцією: ${m.interpolated_cells}.</li><li>Зміщення прив’язки точок, м: ${m.snap_offsets_m.map(number).join(' / ')}. Не включені у довжину.</li>${(route.warnings||[]).map(w=>`<li>${escape(w)}</li>`).join('')}</ul>
<h2>Джерела</h2><p><a href="${escape(route.data_quality?.source)}">${escape(route.data_quality?.source)}</a><br><a href="https://doi.org/10.3133/sim3292">USGS Geologic Map of Mars — SIM 3292</a></p></main></html>`
}
export function downloadReport(result:GlobalRoute){
  const url=URL.createObjectURL(new Blob([reportHtml(result)],{type:'text/html;charset=utf-8'}))
  const a=document.createElement('a');a.href=url;a.download='mars-expedition-report.html';a.click();URL.revokeObjectURL(url)
}
