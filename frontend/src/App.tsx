import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Crosshair, DownloadSimple, GlobeHemisphereWest, Path, Stack, SidebarSimple } from '@phosphor-icons/react'
import { api, loadBundle } from './api'
import { MarsMap, geologyColors } from './components/MarsMap'
import { ElevationChart } from './components/ElevationChart'
import type { Bundle, Dataset, Position, RouteResult, Sample } from './types'
import type { MissionSnapshot } from './components/MissionControl'

type Fields={lon:string;lat:string}
const empty=():Fields=>({lon:'',lat:''})
function parse(p:Fields):Position|null{
  const lon=Number(p.lon),lat=Number(p.lat)
  return p.lon!==''&&p.lat!==''&&Number.isFinite(lon)&&Number.isFinite(lat)&&Math.abs(lon)<=180&&Math.abs(lat)<=90?{lon,lat}:null
}
const messages={
  no_route:'No route meets the selected constraints.',
  blocked_endpoint:'An endpoint is blocked.',
  outside_grid:'An endpoint is outside the selected DEM.',
  search_limit:'Search limit reached.',
}
const number=(n:number,digits=1)=>n.toLocaleString('en-US',{maximumFractionDigits:digits})
const MissionControl=lazy(()=>import('./components/MissionControl'))

export default function App(){
  const missionSession=useRef<MissionSnapshot|null>(null)
  const [bundle,setBundle]=useState<Bundle|null>(null),[bootError,setBootError]=useState(''),[reload,setReload]=useState(0)
  const [dataset,setDataset]=useState<Dataset>('regional')
  const [a,setA]=useState<Fields>(empty),[b,setB]=useState<Fields>(empty),[target,setTarget]=useState<'start'|'end'>('start')
  const [limit,setLimit]=useState(15),[weight,setWeight]=useState(1)
  const [route,setRoute]=useState<RouteResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [sample,setSample]=useState<Sample|null>(null)
  const [plannerOpen,setPlannerOpen]=useState(true),[viewMode,setViewMode]=useState<'2d'|'planet'>('planet')
  const [visible,setVisible]=useState<Record<string,boolean>>({optical:true,science:true})
  const version=useRef(0),controller=useRef<AbortController|null>(null)
  const sampleController=useRef<AbortController|null>(null),sampleVersion=useRef(0)
  const [sampling,setSampling]=useState(false)
  const start=useMemo(()=>parse(a),[a]),end=useMemo(()=>parse(b),[b])
  const bounds=bundle?.layers.terrain[dataset].metadata?.bounds_lon_lat_deg
  const covered=(point:Position|null)=>!point||!!bounds&&point.lon>=bounds[0]&&point.lon<=bounds[2]&&point.lat>=bounds[1]&&point.lat<=bounds[3]
  const outsideCoverage=!covered(start)||!covered(end)
  useEffect(()=>{
    const abort=new AbortController()
    loadBundle(abort.signal).then(data=>{
      setBundle(data)
      if(!data.layers.terrain.regional?.available)setDataset('ctx')
    }).catch(e=>{if(e.name!=='AbortError')setBootError(e.message)})
    return ()=>abort.abort()
  },[reload])
  useEffect(()=>()=>{controller.current?.abort();sampleController.current?.abort()},[])
  function invalidate(){
    version.current++;sampleVersion.current++;controller.current?.abort();sampleController.current?.abort()
    setSampling(false);setBusy(false);setRoute(null);setError('')
  }
  function chooseTarget(which:'start'|'end'){
    sampleVersion.current++;sampleController.current?.abort();setSampling(false);setTarget(which)
  }
  function edit(which:'start'|'end',field:keyof Fields,value:string){
    invalidate();setSample(null)
    const setter=which==='start'?setA:setB
    setter(prev=>({...prev,[field]:value}))
  }
  async function pick(point:Position){
    invalidate();const id=version.current,sampleId=sampleVersion.current,which=target
    setSampling(true);sampleController.current=new AbortController()
    try{
      const p=await api<Sample>(`/api/elevation?dataset=${dataset}&lon=${point.lon}&lat=${point.lat}`,{signal:sampleController.current.signal})
      if(id!==version.current||sampleId!==sampleVersion.current)return
      setSample(p)
      if(!p.valid){setError('No elevation data at this point.');return}
      const values={lon:point.lon.toFixed(6),lat:point.lat.toFixed(6)}
      if(which==='start'){setA(values);setTarget('end')}else setB(values)
    }catch(e){if(id===version.current&&sampleId===sampleVersion.current&&e instanceof Error&&e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current&&sampleId===sampleVersion.current)setSampling(false)}
  }
  async function build(){
    if(!start||!end){setError('Invalid endpoint coordinates.');return}
    invalidate();const id=version.current
    controller.current=new AbortController();setBusy(true)
    try{
      const result=await api<RouteResult>('/api/route',{method:'POST',signal:controller.current.signal,
        headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset,start,end,max_slope_deg:limit,slope_weight:weight,nearby_radius_m:200})})
      if(id!==version.current)return
      if(result.status!=='ok'){setError(messages[result.status]);return}
      setRoute(result)
    }catch(e){if(id===version.current&&e instanceof Error&&e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current)setBusy(false)}
  }
  function download(){
    if(!route?.route)return
    const {traversability:_assessment,warnings:_warnings,warning:_warning,message:_message,...properties}=route.route.properties??{}
    const content={...route.route,properties:{...properties,dataset:route.dataset,
      coordinate_system:'Mars planetocentric, east-positive longitude',model_parameters:route.parameters,metrics:route.metrics}}
    const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/geo+json'}))
    const link=document.createElement('a');link.href=url;link.download='jezero-mars-route.geojson';link.click();URL.revokeObjectURL(url)
  }
  const metrics=route?.metrics
  if(viewMode==='planet')return <Suspense fallback={<div className="panel loading" role="status">Loading atlas…</div>}>
    <MissionControl onLocal={()=>setViewMode('2d')} session={missionSession}/>
  </Suspense>
  return <div className="app">
    <header className="app-header">
      <a href="/" className="brand" aria-label="Mars Explorer home"><GlobeHemisphereWest size={34} weight="duotone" aria-hidden/><span>MARS<span className="brand-light">EXPLORER</span><small>MISSION CONTROL</small></span></a>
      <nav aria-label="Workspace"><button className="text-button" onClick={()=>setViewMode('planet')}>Planet</button><a href="#planner" aria-current="page">Jezero map</a></nav>
      <span className="mission-tag"><span className="live-dot"/> JEZERO / MARS</span>
    </header>
    <main>
      <div className="intro flex items-end justify-between gap-4"><div><p className="eyebrow">LOCAL ATLAS / NASA / USGS</p><h1>Jezero <em>Atlas.</em></h1></div><div className="coverage-note"><span>ROUTING AREA</span><strong>{bundle?.layers.terrain.regional?.available?'≈ 30 × 30 km':'5 × 5 km'}</strong><small>CTX 20 m · HiRISE 1 m</small></div></div>
      {bootError?<section className="panel boot-error" role="alert"><h2>Data unavailable</h2><p>{bootError}</p><button className="primary" onClick={()=>{setBootError('');setReload(x=>x+1)}}>Retry</button></section>
        :!bundle?<section className="panel loading" role="status">Loading Jezero layers…</section>
        :<>
          <div className="workspace-topline"><span>JEZERO MAP</span><button className="workspace-toggle" onClick={()=>setPlannerOpen(x=>!x)} aria-expanded={plannerOpen} aria-controls="planner-panel"><SidebarSimple size={17} aria-hidden/>{plannerOpen?'Expand map':'Show planner'}</button></div>
          <div className={`workspace ${plannerOpen?'':'workspace-map-only'}`} id="planner">
            <aside className="planner panel" id="planner-panel" hidden={!plannerOpen}>
              <div className="section-heading"><span className="step">01</span><h2>Route planner</h2><Path size={22} aria-hidden/></div>
              <label className="field-label" htmlFor="dataset">Routing data</label>
              <select id="dataset" value={dataset} onChange={e=>{invalidate();setDataset(e.target.value as Dataset);setA(empty());setB(empty());setSample(null);setTarget('start')}}>
                <option value="regional" disabled={!bundle.layers.terrain.regional?.available}>CTX regional / 20 m</option>
                <option value="ctx" disabled={!bundle.layers.terrain.ctx.available}>CTX local / 20 m · 5 × 5 km</option>
                <option value="hirise" disabled={!bundle.layers.terrain.hirise.available}>HiRISE / 1 m</option>
              </select>
              {([['start','A','Start',a],['end','B','End',b]] as const).map(([which,letter,title,fields])=><div key={which} className={`endpoint ${target===which?'endpoint-active':''}`}>
                <button className="endpoint-title" onClick={()=>chooseTarget(which)} aria-pressed={target===which}><span className={`point-badge ${which}`}>{letter}</span><strong>{title}</strong><Crosshair size={18} aria-hidden/></button>
                <div className="coordinate-fields"><label>Longitude E<input aria-label={`${title}: longitude`} type="number" step="any" min="-180" max="180" value={fields.lon} onChange={e=>edit(which,'lon',e.target.value)}/></label><label>Latitude N<input aria-label={`${title}: latitude`} type="number" step="any" min="-90" max="90" value={fields.lat} onChange={e=>edit(which,'lat',e.target.value)}/></label></div>
              </div>)}
              <button className="text-button" disabled={!start&&!end} onClick={()=>{invalidate();setSample(null);setA(b);setB(a);setTarget('start')}}>Swap A ↔ B</button>
              <div className="parameter-label"><label htmlFor="slope">Maximum slope</label><output htmlFor="slope">{limit}°</output></div>
              <input id="slope" type="range" min="0" max="45" step="1" value={limit} onChange={e=>{invalidate();setLimit(Number(e.target.value))}}/>
              <details className="model-details"><summary>Parameters</summary><label className="field-label" htmlFor="weight">Slope weight</label><select id="weight" value={weight} onChange={e=>{invalidate();setWeight(Number(e.target.value))}}><option value="0">Distance only</option><option value="1">Balanced · 1</option><option value="5">Lower slopes · 5</option></select></details>
              <button className="primary build-button" onClick={build} disabled={!start||!end||busy}>{busy?'Calculating…':'Build route'}<ArrowRight size={20} aria-hidden/></button>
              <button className="text-button" onClick={()=>{invalidate();setA(empty());setB(empty());setSample(null);setTarget('start')}}>Clear plan</button>
              {(error||busy)&&<div role={error?'alert':'status'} aria-live="polite" className={`plan-status ${error?'error':''}`}>{error||'Calculating…'}</div>}
            </aside>
            <section className="map-column" aria-label="Jezero map and layers">
              <div className={`map-interaction panel ${error?'map-interaction-error':''}`}>
                <div className="map-pick-target" role="group" aria-label="Selected endpoint"><button aria-pressed={target==='start'} onClick={()=>chooseTarget('start')}>A · Start</button><button aria-pressed={target==='end'} onClick={()=>chooseTarget('end')}>B · End</button></div>
                {sampling&&<span role="status">Sampling…</span>}
                {outsideCoverage&&<p className="coverage-status" role="status">Endpoint outside {dataset.toUpperCase()} coverage.</p>}
                {error&&!plannerOpen&&<p role="alert">{error}</p>}
                {busy&&<div className="map-search-status"><span role="status">Calculating…</span><button className="text-button" onClick={invalidate}>Cancel</button></div>}
              </div>
              <MarsMap bundle={bundle} dataset={dataset} start={start} end={end} route={route} visible={visible} focus={null} onPick={pick}/>
              <div className="map-toolbar panel"><span className="toolbar-label"><Stack size={18} aria-hidden/> Layers</span>
                {([['optical','CTX imagery'],[`${dataset}-elevation`,'Elevation'],[`${dataset}-slope`,'Slopes'],['geology','Geology'],['science','Science regions']] as const).map(([key,label])=><label className={`layer-chip ${visible[key]?'selected':''}`} key={key}><input type="checkbox" checked={!!visible[key]} onChange={e=>setVisible(prev=>({...prev,[key]:e.target.checked}))}/>{label}</label>)}
                {sample?.valid&&<span className="sample-readout">{number(sample.elevation_m!)} m / {number(sample.slope_deg!)}°</span>}
              </div>
              <details className="legend panel"><summary>Layer legends</summary><div className="legend-grid">{(bundle.overlays[dataset]?.overlays||[]).map(x=><div key={x.name}><span>{x.name==='elevation'?'Elevation':'Slope'} · {x.legend.units}</span><div className={`color-ramp ${x.name}`}/><small>{number(x.legend.min)} — {number(x.legend.max)}</small></div>)}<div>{bundle.layers.geology.legend.map((g,i)=><p key={g.name}><i style={{background:geologyColors[i%geologyColors.length]}}/>{g.name}</p>)}</div></div></details>
            </section>
          </div>
          {route&&metrics&&<section className="results panel" aria-labelledby="results-heading">
            <div className="section-heading"><span className="step">02</span><h2 id="results-heading">Route results</h2><Path size={22} aria-hidden/><button className="text-button export-button" onClick={download}><DownloadSimple size={17} aria-hidden/>Export GeoJSON</button></div>
            <div className="stats-grid" data-testid="route-summary">{[['Distance',`${number(metrics.distance_m)} m`],['Ascent / descent',`+${number(metrics.ascent_m)} / −${number(metrics.descent_m)} m`],['Elevation',`${number(metrics.min_elevation_m)} … ${number(metrics.max_elevation_m)} m`],['Maximum slope',`${number(metrics.max_slope_deg)}°`]].map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
            <div className="profile-heading"><h3>Elevation profile</h3></div><ElevationChart result={route}/>
          </section>}
        </>}
    </main>
  </div>
}
