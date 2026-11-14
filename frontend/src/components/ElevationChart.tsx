import { useEffect, useRef, useState } from 'react'
import type { RouteResult } from '../types'

export function ElevationChart({ result }: { result: RouteResult }) {
  const host = useRef<HTMLDivElement>(null)
  const [error,setError] = useState('')
  const profile = result.metrics!.elevation_profile
  useEffect(()=>{
    let disposed=false
    let cleanup=()=>{}
    import('plotly.js-basic-dist-min').then(async ({default:Plotly})=>{
      if(disposed) return
      const div=host.current!
      await Plotly.react(div,[{
        x:profile.map(p=>p.distance_m),y:profile.map(p=>p.elevation_m),type:'scatter',mode:'lines',
        fill:'tozeroy',fillcolor:'rgba(232,155,104,0.08)',line:{color:'#f5b079',width:2},
        hovertemplate:'%{x:.0f} м<br>%{y:.2f} м<extra></extra>',
      }],{
        autosize:true,height:220,paper_bgcolor:'transparent',plot_bgcolor:'transparent',
        font:{family:'system-ui',color:'#aeb7c3',size:11},margin:{l:60,r:16,t:12,b:40},
        xaxis:{title:{text:'Відстань, м'},gridcolor:'#2b3138',zeroline:false},
        yaxis:{title:{text:'Висота, м'},gridcolor:'#2b3138',zeroline:false,range:[Math.min(...profile.map(p=>p.elevation_m))-1,Math.max(...profile.map(p=>p.elevation_m))+1]},
      },{responsive:true,displayModeBar:false})
      if(disposed){Plotly.purge(div);return}
      const observer=new ResizeObserver(()=>{void Plotly.Plots.resize(div)})
      observer.observe(div)
      cleanup=()=>{observer.disconnect();Plotly.purge(div)}
    }).catch(()=>{if(!disposed)setError('Графік недоступний. Числові дані наведені в таблиці.')})
    return ()=>{disposed=true;cleanup()}
  },[profile])
  return <>
    {error && <p role="alert">{error}</p>}
    <div ref={host} className="profile-chart" data-testid="elevation-chart" role="img" aria-label="Профіль висот розрахованого A* маршруту" />
    <details className="profile-table"><summary>Числовий профіль ({profile.length} клітинок)</summary>
      <div className="table-scroll"><table><thead><tr><th>Відстань, м</th><th>Висота, м</th><th>Ухил, °</th></tr></thead>
        <tbody>{profile.map((p,i)=><tr key={i}><td>{p.distance_m.toFixed(1)}</td><td>{p.elevation_m.toFixed(2)}</td><td>{p.slope_deg.toFixed(2)}</td></tr>)}</tbody>
      </table></div>
    </details>
  </>
}
