import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { ArrowRight, ArrowsLeftRight, BookmarkSimple, CircleNotch, DownloadSimple, GlobeHemisphereWest, Mountains, NavigationArrow, Path, Planet, X, Play, Pause, MapTrifold, Plus, FileText, ShareNetwork } from '@phosphor-icons/react'
import MarsGlobe from './MarsGlobe'
import AtlasMap from './AtlasMap'
import { downloadReport } from './expeditionReport'
import { api, assetUrl } from '../api'
import type { GlobalRoute, Position, AtlasCatalog, GeologicalUnit } from '../types'
import './mission.css'

type Fields={lon:string;lat:string}
export type MissionSnapshot={a:Fields;b:Fields;target:'a'|'b'|'stop';focus:Position|null;weight:number;grade:number;result:GlobalRoute|null;alternative:GlobalRoute|null;stops?:Position[];resolution?:string}
const blank=():Fields=>({lon:'',lat:''})
const fields=(p:Position):Fields=>({lon:p.lon.toFixed(6),lat:p.lat.toFixed(6)})
function position(p:Fields):Position|null{
  const lon=Number(p.lon),lat=Number(p.lat)
  return p.lon.trim()!==''&&p.lat.trim()!==''&&Number.isFinite(lon)&&Number.isFinite(lat)&&Math.abs(lon)<=180&&Math.abs(lat)<=90?{lon,lat}:null
}
const format=(v:number,d=0)=>v.toLocaleString('en-US',{maximumFractionDigits:d})
const km=(v:number)=>`${format(v/1000,1)} km`
const routeErrors={no_route:'No route meets the selected constraints.',search_limit:'Search limit reached.',blocked_endpoint:'An endpoint is blocked.',outside_grid:'An endpoint is outside the selected DEM.'}

function Profile({result,index,onIndex}:{result:GlobalRoute;index:number;onIndex:(v:number)=>void}){
  const profile=result.profile!
  const low=profile.reduce((v,p)=>Math.min(v,p.elevation_m),Infinity),high=profile.reduce((v,p)=>Math.max(v,p.elevation_m),-Infinity)
  const total=profile[profile.length-1].distance_m||1
  const point=profile[Math.min(index,profile.length-1)]
  const x=(d:number)=>20+d/total*760,y=(h:number)=>110-(h-low)/Math.max(1,high-low)*85
  const line=profile.map(p=>`${x(p.distance_m)},${y(p.elevation_m)}`).join(' ')
  return <div className="mc-profile">
    <div className="mc-section-title"><span>ELEVATION PROFILE</span><span>{km(point.distance_m)} · <b>{format(point.elevation_m)} m</b></span></div>
    <svg viewBox="0 0 800 135" role="img" aria-label={`Route elevation: ${low} to ${high} metres`}>
      <defs><linearGradient id="profile-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="var(--mc-copper)" stopOpacity=".28"/><stop offset="1" stopColor="var(--mc-copper)" stopOpacity="0"/></linearGradient></defs>
      {[25,65,110].map(v=><line key={v} x1="20" x2="780" y1={v} y2={v} stroke="var(--mc-line)" strokeDasharray="3 6"/>)}
      <polygon points={`20,115 ${line} ${x(total)},115`} fill="url(#profile-fill)"/>
      <polyline points={line} fill="none" stroke="var(--mc-copper)" strokeWidth="2"/>
      <line x1={x(point.distance_m)} x2={x(point.distance_m)} y1="15" y2="115" stroke="var(--mc-mint)" strokeDasharray="3 4"/>
      <circle cx={x(point.distance_m)} cy={y(point.elevation_m)} r="4" fill="var(--mc-mint)"/>
      <text x="20" y="132" fill="var(--mc-muted)" fontSize="10">A / 0 km</text><text x="780" y="132" textAnchor="end" fill="var(--mc-muted)" fontSize="10">B / {km(total)}</text>
    </svg>
    <input aria-label="Elevation profile position" type="range" min="0" max={profile.length-1} value={Math.min(index,profile.length-1)} onChange={e=>onIndex(Number(e.target.value))}/>
  </div>
}

export default function MissionControl({onLocal,session}:{onLocal:()=>void;session:RefObject<MissionSnapshot|null>}){
  const saved=session.current
  const [terrain,setTerrain]=useState<{equatorial_spacing_m:number}|null>(null),[dataError,setDataError]=useState(''),[retry,setRetry]=useState(0)
  const [a,setA]=useState<Fields>(saved?.a??blank),[b,setB]=useState<Fields>(saved?.b??blank),[target,setTarget]=useState<'a'|'b'|'stop'>(saved?.target??'a')
  const [focus,setFocus]=useState<Position|null>(saved?.focus??{lon:-105,lat:15})
  const [inspectionPoint,setInspectionPoint]=useState<Position|null>(focus)
  const [weight,setWeight]=useState(saved?.weight??5),[grade,setGrade]=useState(saved?.grade??15),[result,setResult]=useState<GlobalRoute|null>(saved?.result??null),[alternative,setAlternative]=useState<GlobalRoute|null>(saved?.alternative??null)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const [catalog,setCatalog]=useState<AtlasCatalog|null>(null),[atlasError,setAtlasError]=useState('')
  const [view,setView]=useState<'globe'|'map'>('globe'),[layer,setLayer]=useState('auto'),[geology,setGeology]=useState(false)
  const [stops,setStops]=useState<Position[]>(saved?.stops??[]),[resolution,setResolution]=useState(saved?.resolution??'auto')
  const [units,setUnits]=useState<GeologicalUnit[]>([]),[playing,setPlaying]=useState(false),[flight,setFlight]=useState<number|null>(null)
  const [share,setShare]=useState(''),[copied,setCopied]=useState(false)
  const [sample,setSample]=useState<{elevation_m:number;observations:number|null;interpolated:boolean;dataset:string;spacing_m:number;slope_deg?:number}|null>(null)
  const controller=useRef<AbortController|null>(null),version=useRef(0),sampleVersion=useRef(0)
  const start=position(a),end=position(b)
  useEffect(()=>{session.current={a,b,target,focus,weight,grade,result,alternative,stops,resolution}},[a,b,target,focus,weight,grade,result,alternative,stops,resolution,session])
  useEffect(()=>{
    const abort=new AbortController()
    api<AtlasCatalog>('/api/atlas',{signal:abort.signal}).then(setCatalog).catch(e=>{if(e.name!=='AbortError')setAtlasError(e.message)})
    const encoded=new URLSearchParams(location.hash.slice(1)).get('mission')
    if(encoded&&!saved){
      try{
        const data=JSON.parse(decodeURIComponent(atob(encoded)))
        const pa=fields(data.start),pb=fields(data.end)
        if(!position(pa)||!position(pb)||!Array.isArray(data.stops)||data.stops.length>4||data.stops.some((p:Position)=>!position(fields(p))))throw Error()
        if(![0,5,20].includes(data.weight)||!Number.isFinite(data.grade)||data.grade<0||data.grade>45)throw Error()
        if(data.resolution&&!['auto','mola','regional','hirise'].includes(data.resolution))throw Error()
        setA(pa);setB(pb);setStops(data.stops.map((p:Position)=>({lon:p.lon,lat:p.lat})));setWeight(data.weight);setGrade(data.grade);setResolution(data.resolution??'auto');setFocus(data.start);setTarget('b')
        setNotice('Shared plan loaded.')
      }catch{setNotice('Invalid shared plan.')}
    }
    return ()=>abort.abort()
  },[])
  useEffect(()=>{
    if(!playing||!result?.profile?.length)return
    let frame=0,last=performance.now(),progress=flight??0
    const animate=(now:number)=>{
      if(document.hidden){last=now;frame=requestAnimationFrame(animate);return}
      progress=Math.min(1,progress+(now-last)/24000);last=now;setFlight(progress)
      if(progress<1)frame=requestAnimationFrame(animate)
      else setPlaying(false)
    }
    frame=requestAnimationFrame(animate)
    return ()=>cancelAnimationFrame(frame)
  },[playing,result])
  useEffect(()=>{
    const abort=new AbortController();setDataError('')
    api<{equatorial_spacing_m:number}>('/api/global',{signal:abort.signal}).then(setTerrain).catch(e=>{if(e.name!=='AbortError')setDataError(e.message)})
    return ()=>abort.abort()
  },[retry])
  useEffect(()=>()=>{controller.current?.abort();version.current++},[])
  useEffect(()=>{setInspectionPoint(focus)},[focus])
  useEffect(()=>{
    const abort=new AbortController(),id=++sampleVersion.current
    if(!inspectionPoint)return
    setSample(null)
    api<{elevation:typeof sample;geology:GeologicalUnit[]}>(`/api/atlas/inspect?lon=${inspectionPoint.lon}&lat=${inspectionPoint.lat}`,{signal:abort.signal})
      .then(value=>{if(id===sampleVersion.current){setSample(value.elevation);setUnits(value.geology)}}).catch(()=>{setUnits([])})
    return ()=>abort.abort()
  },[inspectionPoint,retry])
  function invalidate(){
    controller.current?.abort();version.current++;setBusy(false);setResult(null);setAlternative(null);setError('');setNotice('');setPlaying(false);setFlight(null);setShare('')
  }
  function pick(p:Position){
    invalidate()
    if(target==='stop'){
      if(stops.length>=4){setNotice('Maximum of four stops.');return}
      setStops(prev=>[...prev,{lon:p.lon,lat:p.lat}]);setTarget('b')
    }else{(target==='a'?setA:setB)(fields(p));if(target==='a')setTarget('b')}
    setInspectionPoint(p)
  }
  function showAtlas(){
    document.querySelector('.mc-observatory')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})
  }
  async function build(compare=false){
    if(!start||!end)return
    invalidate();const id=version.current,abort=new AbortController();controller.current=abort;setBusy(true)
    const request=(slope_weight:number)=>api<GlobalRoute>('/api/expedition',{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({start,end,stops,resolution,slope_weight,max_grade_deg:grade})})
    try{
      const primary=await request(weight)
      if(id!==version.current)return
      if(primary.status!=='ok'){setResult(primary);setError(routeErrors[primary.status]);return}
      setResult(primary)
      if(compare){
        const second=await request(weight===0?20:0)
        if(id!==version.current)return
        if(second.status==='ok')setAlternative(second)
        else setNotice(`Alternative: ${routeErrors[second.status]}`)
      }
    }catch(e){if(id===version.current&&e instanceof Error&&e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current)setBusy(false)}
  }
  function save(){
    if(!start||!end)return
    try{localStorage.setItem('mars-explorer-mission-v1',JSON.stringify({start,end,weight,grade,stops,resolution}));setNotice('Plan saved.')}
    catch{setNotice('Plan could not be saved.')}
  }
  function restore(){
    try{
      const stored=JSON.parse(localStorage.getItem('mars-explorer-mission-v1')||'null')
      if(!stored)throw Error()
      const a=fields(stored.start),b=fields(stored.end)
      if(!position(a)||!position(b)||![0,5,20].includes(stored.weight)||!Number.isFinite(stored.grade)||stored.grade<0||stored.grade>45)throw Error()
      const restoredStops=stored.stops??[]
      if(!Array.isArray(restoredStops)||restoredStops.length>4||restoredStops.some((p:Position)=>!position(fields(p))))throw Error()
      if(stored.resolution&&!['auto','mola','regional','hirise'].includes(stored.resolution))throw Error()
      invalidate();setStops(restoredStops.map((p:Position)=>({lon:p.lon,lat:p.lat})));setResolution(stored.resolution??'auto');setA(a);setB(b);setTarget('b');setWeight(stored.weight);setGrade(stored.grade);setFocus(stored.start);setNotice('Plan restored.')
    }catch{setNotice('No saved plan found.')}
  }
  function download(){
    if(!result?.route)return
    const {traversability:_assessment,warnings:_warnings,message:_message,...properties}=result.route.properties??{}
    const {rule:_rule,...policy}=result.hazard_policy??{}
    const file={...result.route,properties:{...properties,coordinate_system:'Mars planetocentric, east-positive longitude',metrics:result.metrics,
      hazard_policy:policy,terrain_validation:result.terrain_validation,fine_terrain_checks:result.terrain_checks,
      profile_sources:result.profile?.map(p=>({dataset:p.dataset??result.dataset,interpolated:p.interpolated}))}}
    const url=URL.createObjectURL(new Blob([JSON.stringify(file,null,2)],{type:'application/geo+json'}))
    const link=document.createElement('a');link.href=url;link.download='mars-global-expedition.geojson';link.click();URL.revokeObjectURL(url)
  }
  function sharePlan(){
    if(!start||!end)return
    const url=new URL(location.href);url.hash=new URLSearchParams({mission:btoa(encodeURIComponent(JSON.stringify({start,end,stops,weight,grade,resolution})))}).toString()
    setShare(url.toString());setCopied(false)
  }
  const metrics=result?.metrics
  const flightIndex=result?.profile?Math.max(0,result.profile.findIndex(p=>p.distance_m>=(flight??0)*result.profile![result.profile!.length-1].distance_m)):0
  return <div className="mission-control">
    <a className="mc-skip" href="#mission-plan">Skip to route planner</a>
    <header className="mc-header">
      <a className="mc-brand" href="/"><span className="mc-brand-symbol"><Planet size={30} aria-hidden/></span><span>MARS<span>EXPLORER</span><small>MISSION CONTROL</small></span></a>
      <nav aria-label="Workspace"><button className="active" aria-current="page"><GlobeHemisphereWest size={17} aria-hidden/>Planet</button><button onClick={onLocal}><Mountains size={17} aria-hidden/>Jezero map</button></nav>
      <div className="mc-system" role="status" data-state={dataError?'error':terrain?'ready':'loading'}><i aria-hidden/>{terrain?'MOLA / READY':dataError?'MOLA / UNAVAILABLE':'MOLA / LOADING'}</div>
    </header>
    <main className="mc-main">
      <section className="mc-intro"><div><div className="mc-kicker"><span><i className="mc-live"/> PLANETARY ATLAS</span><span>NASA / USGS</span></div><h1>Mars <em>Atlas.</em></h1></div><div className="mc-planet-facts"><div><strong>144.8<span> million km²</span></strong><small>SURFACE AREA</small></div><div><strong>463<span> m</span></strong><small>PLANETARY DEM SPACING</small></div></div></section>
      <div className="mc-workspace">
        <aside className="mc-planner" id="mission-plan">
          <div className="mc-panel-heading"><NavigationArrow size={20} aria-hidden/><h2>Route planner</h2><span>01 / PLAN</span></div>
          <div className="mc-endpoints">
            {([['a','A','Start',a],['b','B','End',b]] as const).map(([key,letter,label,value])=><div key={key} className={`mc-endpoint ${target===key?'selected':''}`}>
              <button onClick={()=>setTarget(key)} aria-pressed={target===key}><span className={`mc-pin ${key}`}>{letter}</span><strong>{label}</strong></button>
              <div className="mc-coordinate-fields">{(['lon','lat'] as const).map(field=><label key={field}>{field==='lon'?'Longitude E':'Latitude N'}<input aria-label={`${label}: ${field==='lon'?'longitude':'latitude'}`} type="number" step="any" min={field==='lon'?-180:-90} max={field==='lon'?180:90} value={value[field]} onChange={e=>{invalidate();(key==='a'?setA:setB)(p=>({...p,[field]:e.target.value}))}}/></label>)}</div>
            </div>)}
          </div>
          <div className="mc-inline-actions"><button onClick={()=>{invalidate();setA(b);setB(a);setStops(prev=>[...prev].reverse())}} aria-label="Swap A and B"><ArrowsLeftRight size={16} aria-hidden/>Swap</button><button onClick={()=>{invalidate();setA(blank());setB(blank());setStops([]);setTarget('a')}}><X size={14} aria-hidden/>Clear</button></div>
          <div className="mc-stops">
            {stops.map((stop,i)=><div key={i}><span>{i+1}</span><div className="mc-stop-fields">{(['lon','lat'] as const).map(field=><label key={field}>{field==='lon'?'E':'N'}<input aria-label={`Stop ${i+1}: ${field==='lon'?'longitude':'latitude'}`} type="number" step="any" min={field==='lon'?-180:-90} max={field==='lon'?180:90} value={stop[field]} onChange={e=>{const value=e.target.valueAsNumber;if(!Number.isFinite(value))return;invalidate();setStops(prev=>prev.map((s,j)=>j===i?{...s,[field]:value}:s))}}/></label>)}</div><button aria-label={`Move stop ${i+1} up`} disabled={i===0} onClick={()=>{invalidate();setStops(prev=>{const next=[...prev];[next[i-1],next[i]]=[next[i],next[i-1]];return next})}}>↑</button><button aria-label={`Remove stop ${i+1}`} onClick={()=>{invalidate();setStops(prev=>prev.filter((_,j)=>j!==i))}}><X size={13}/></button></div>)}
            <button className="mc-secondary" disabled={stops.length>=4} aria-pressed={target==='stop'} onClick={()=>setTarget(target==='stop'?'b':'stop')}><Plus size={15} aria-hidden/>{target==='stop'?'Stop selection':'Add stop'}</button>
          </div>
          <label className="mc-label" htmlFor="global-resolution">ROUTING DATA</label>
          <select id="global-resolution" value={resolution} onChange={e=>{invalidate();setResolution(e.target.value)}}><option value="auto">Auto · best available DEM</option><option value="mola">MOLA · planetary</option><option value="regional">CTX 20 m · Jezero</option><option value="hirise">HiRISE 1 m · local</option></select>
          <label className="mc-label" htmlFor="global-strategy">ROUTE STRATEGY</label>
          <select id="global-strategy" value={weight} onChange={e=>{invalidate();setWeight(Number(e.target.value))}}><option value="0">Shortest distance</option><option value="5">Balanced</option><option value="20">Lower elevation changes</option></select>
          <details className="mc-parameters"><summary>Parameters <span>{grade}°</span></summary><label htmlFor="global-grade">Maximum slope</label><input id="global-grade" type="range" min="0" max="45" value={grade} onChange={e=>{invalidate();setGrade(Number(e.target.value))}}/></details>
          <button className="mc-primary" onClick={()=>void build()} disabled={!start||!end||!terrain||busy} aria-busy={busy}>{busy?<><CircleNotch className="mc-spinner" size={19} aria-hidden/>Calculating…</>:<>Build route<ArrowRight size={19} aria-hidden/></>}</button>
          {busy?<button className="mc-secondary" onClick={()=>{invalidate();setNotice('Request cancelled.')}}>Cancel</button>:<button className="mc-secondary" onClick={()=>void build(true)} disabled={!start||!end||!terrain}><Path size={17} aria-hidden/>Compare strategies</button>}
          {(error||notice)&&<div className="mc-feedback" role={error?'alert':'status'}>{error||notice}</div>}
          <div className="mc-save"><button onClick={save} disabled={!start||!end}><BookmarkSimple size={15} aria-hidden/>Save</button><button onClick={restore}>Restore plan</button></div>
        </aside>
        <section className="mc-observatory" aria-label="Planetary atlas">
          <div className="mc-map-topline"><div><span className="mc-live"/><span>MARS ATLAS</span></div><div className="mc-layer-switch" role="group" aria-label="Atlas view"><button aria-pressed={view==='globe'} onClick={()=>setView('globe')}><GlobeHemisphereWest size={16} aria-hidden/>Globe</button><button aria-pressed={view==='map'} onClick={()=>{setPlaying(false);setView('map')}}><MapTrifold size={16} aria-hidden/>2D atlas</button></div></div>
          <div className="mc-atlas-toolbar">
            {view==='map'&&<label>Imagery<select aria-label="Imagery layer" value={layer} onChange={e=>setLayer(e.target.value)}><option value="auto">Auto · Viking → CTX → HiRISE</option><option value="viking">Viking · local mosaic</option>{catalog?.tiles.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>}
            <label className="mc-geology-toggle"><input type="checkbox" checked={geology} onChange={e=>setGeology(e.target.checked)} disabled={!catalog}/>USGS geology</label>
            <button className="mc-text" onClick={()=>{setView('map');setFocus({lon:77.4508,lat:18.4447})}}>Jezero →</button>
          </div>
          {view==='globe'?<MarsGlobe start={start} end={end} onPick={pick} onFallback={()=>setView('map')} route={result} focus={focus} geology={geology} flightProgress={flight} catalog={catalog}/>:<AtlasMap catalog={catalog} layer={layer} geology={geology} start={start} end={end} stops={stops} route={result} focus={focus} onPick={pick} onLocal={onLocal}/>}
          <div className="mc-telemetry"><div><span>ELEVATION · {sample?.dataset?.toUpperCase()??'DEM'}</span><strong>{sample?`${format(sample.elevation_m)} m`:'—'}</strong>{sample&&<small>{format(sample.spacing_m)} m / cell</small>}</div></div>
          {geology&&<div className="mc-geology-info"><span className="mc-chip">USGS SIM 3292 / 1:20M</span><strong>{units.map(u=>u.unit).join(' · ')||'—'}</strong>{units.map(u=><p key={u.id}><i style={{background:u.color}}/>{u.description}</p>)}<details><summary>Legend ({catalog?.legend.length??0} units)</summary><div className="mc-geology-legend">{catalog?.legend.map(u=><span key={u.unit}><i style={{background:u.color}}/><b>{u.unit}</b> {u.description}</span>)}</div></details></div>}
          {dataError&&<div className="mc-feedback" role="alert">{dataError}<button className="mc-secondary" onClick={()=>setRetry(x=>x+1)}>Retry MOLA</button></div>}
          {atlasError&&<div className="mc-feedback" role="alert">{atlasError}</div>}
          <div className="mc-metrics" data-testid={metrics?'global-route-summary':undefined}>
            <div><span>DISTANCE</span><strong>{metrics?km(metrics.distance_m):'—'}<small> A → B</small></strong></div>
            <div><span>ASCENT</span><strong>{metrics?`${format(metrics.ascent_m)} m`:'—'}</strong></div>
            <div><span>MAXIMUM SLOPE</span><strong>{metrics?`${format(metrics.max_surface_slope_deg??metrics.max_grade_deg,2)}°`:'—'}</strong></div>
            <div><span>COMPUTATION / CPU</span><strong>{busy?'SEARCHING':result?.elapsed_ms!==undefined?`${format(result.elapsed_ms/1000,2)} s`:'IDLE'}</strong></div>
          </div>
        </section>
      </div>
      {result?.metrics&&<section className="mc-results">
        <div className="mc-result-heading"><div><span className="mc-kicker">02 / ANALYSIS</span><h2>Route results</h2></div><div className="mc-result-actions"><button className="mc-secondary" onClick={download}><DownloadSimple size={18} aria-hidden/>Export GeoJSON</button><button className="mc-secondary" onClick={()=>{downloadReport(result);setNotice('Report saved.')}}><FileText size={18} aria-hidden/>Report / PDF</button><button className="mc-secondary" onClick={sharePlan}><ShareNetwork size={18} aria-hidden/>Share / QR</button></div></div>
        <div className="mc-flight-controls"><button className="mc-secondary" disabled={result.route?.geometry.type!=='LineString'} aria-pressed={playing} onClick={()=>{setView('globe');if((flight??0)>=1)setFlight(0);setPlaying(!playing)}}>{playing?<Pause size={17} aria-hidden/>:<Play size={17} aria-hidden/>}{playing?'Pause':'Route flyover'}</button><button className="mc-text" onClick={()=>{setPlaying(false);setFlight(null);setFocus(start)}}>Reset view</button><span>{Math.round((flight??0)*100)}%</span></div>
        {!!result.profile?.length&&<Profile result={result} index={flightIndex} onIndex={i=>{setPlaying(false);setView('globe');const p=result.profile![i];const total=result.profile![result.profile!.length-1].distance_m;setFlight(total?p.distance_m/total:0)}}/>}
        <div className="mc-route-notes"><span>{format(metrics!.cells)} cells · {result.data_quality?.product||result.dataset}</span><span>Endpoint offsets: {metrics!.snap_offsets_m.map(km).join(' / ')}</span></div>
        {!!result.legs?.length&&<div className="mc-leg-list">{result.legs.map(l=><div key={l.index}><span>LEG {l.index+1}</span><strong>{km(l.distance_m)}</strong><small>Ascent {format(l.ascent_m)} m</small></div>)}</div>}
        {!!result.geological_units?.length&&<details className="mc-route-geology"><summary>Route geology · {result.geological_units.length} units</summary>{result.geological_units.map(u=><p key={u.unit}><i style={{background:u.color}}/><b>{u.unit}</b> — {u.description}</p>)}<a href="https://doi.org/10.3133/sim3292" target="_blank" rel="noreferrer">USGS SIM 3292 ↗</a></details>}
        {share&&<section className="mc-share" aria-label="Share route"><div><h3>Share route</h3><input aria-label="Route link" readOnly value={share}/><button className="mc-secondary" onClick={()=>{navigator.clipboard?.writeText(share).then(()=>setCopied(true)).catch(()=>setNotice('Clipboard unavailable.'))}}>{copied?'Copied':'Copy link'}</button></div><img src={assetUrl(`/api/share/qr?url=${encodeURIComponent(share)}`)} alt="Route QR code"/></section>}
        {alternative?.metrics&&<div className="mc-comparison"><h3>Strategy comparison</h3><div>{[[result,'Current strategy'],[alternative,'Alternative strategy']].map(([r,title],i)=>{const route=r as GlobalRoute;return <button key={i} onClick={()=>{if(i===1){setPlaying(false);setFlight(null);setResult(alternative);setAlternative(result);setShare('');const selectedWeight=alternative.route?.properties?.slope_weight;if([0,5,20].includes(selectedWeight))setWeight(selectedWeight)}}} aria-pressed={i===0}><span>{String(title)}</span><strong>{km(route.metrics!.distance_m)}</strong><small>Ascent {format(route.metrics!.ascent_m)} m · slope {format(route.metrics!.max_grade_deg,2)}°</small><b>{i===0?'Selected':'Show route →'}</b></button>})}</div></div>}
      </section>}
    </main>
    <nav className="mc-mobile-nav" aria-label="Atlas navigation"><button onClick={showAtlas}><GlobeHemisphereWest size={18} aria-hidden/>Atlas</button><button onClick={()=>document.getElementById('mission-plan')?.scrollIntoView({block:'start'})}><NavigationArrow size={18} aria-hidden/>Plan</button><button disabled={!result?.metrics} onClick={()=>document.querySelector('.mc-results')?.scrollIntoView({block:'start'})}><Path size={18} aria-hidden/>Results</button></nav>
  </div>
}
