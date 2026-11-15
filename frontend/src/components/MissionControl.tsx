import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { ArrowRight, ArrowUpRight, ArrowsLeftRight, BookmarkSimple, Check, CircleNotch, Compass, DownloadSimple, GlobeHemisphereWest, Mountains, NavigationArrow, Path, Planet, Sparkle, X, Play, Pause, MapTrifold, Plus, FileText, ShareNetwork, ShieldCheck } from '@phosphor-icons/react'
import MarsGlobe from './MarsGlobe'
import AtlasMap from './AtlasMap'
import { downloadReport } from './expeditionReport'
import { strategicRoute, traversabilityNotice } from './routeAssessment'
import { api } from '../api'
import { assetUrl } from '../api'
import type { GlobalRoute, GlobalTerrainData, Position, AtlasCatalog, GeologicalUnit } from '../types'
import './mission.css'

const places=[
  {name:'Olympus Mons',label:'Найвищий вулкан',lon:-133.8,lat:18.65,tag:'01 / THARSIS'},
  {name:'Valles Marineris',label:'Світ великих каньйонів',lon:-59.2,lat:-14,tag:'02 / CANYONS'},
  {name:'Hellas Planitia',label:'Глибока ударна западина',lon:70,lat:-42,tag:'03 / IMPACT BASIN'},
  {name:'Jezero Crater',label:'Дельта давньої річки',lon:77.4508,lat:18.4447,tag:'04 / PERSEVERANCE'},
  {name:'Gale Crater',label:'Експедиція Curiosity',lon:137.4,lat:-4.6,tag:'05 / CURIOSITY'},
  {name:'Elysium Planitia',label:'Вулканічна рівнина',lon:135.9,lat:4.5,tag:'06 / ELYSIUM'},
]
type Fields={lon:string;lat:string}
export type MissionSnapshot={a:Fields;b:Fields;target:'a'|'b'|'stop';focus:Position|null;topography:boolean;scale:number;weight:number;grade:number;result:GlobalRoute|null;alternative:GlobalRoute|null;stops?:Position[];resolution?:string}
const blank=():Fields=>({lon:'',lat:''})
const fields=(p:Position):Fields=>({lon:p.lon.toFixed(6),lat:p.lat.toFixed(6)})
function position(p:Fields):Position|null{
  const lon=Number(p.lon),lat=Number(p.lat)
  return p.lon.trim()!==''&&p.lat.trim()!==''&&Number.isFinite(lon)&&Number.isFinite(lat)&&Math.abs(lon)<=180&&Math.abs(lat)<=90?{lon,lat}:null
}
const format=(v:number,d=0)=>v.toLocaleString('uk-UA',{maximumFractionDigits:d})
const km=(v:number)=>`${format(v/1000,1)} км`
const routeErrors={no_route:'За цим порогом градієнта шляху немає. Змініть точки або поріг.',search_limit:'Досягнуто бюджету пошуку. Спробуйте коротшу експедицію.',blocked_endpoint:'Точка на непрохідній клітинці CTX. Оберіть іншу точку або параметри.',outside_grid:'Точка поза обраною сіткою.'}

function Profile({result,index,onIndex}:{result:GlobalRoute;index:number;onIndex:(v:number)=>void}){
  const profile=result.profile!
  const low=profile.reduce((v,p)=>Math.min(v,p.elevation_m),Infinity),high=profile.reduce((v,p)=>Math.max(v,p.elevation_m),-Infinity)
  const total=profile[profile.length-1].distance_m||1
  const point=profile[Math.min(index,profile.length-1)]
  const x=(d:number)=>20+d/total*760,y=(h:number)=>110-(h-low)/Math.max(1,high-low)*85
  const line=profile.map(p=>`${x(p.distance_m)},${y(p.elevation_m)}`).join(' ')
  return <div className="mc-profile">
    <div className="mc-section-title"><span>ПРОФІЛЬ ЕКСПЕДИЦІЇ</span><span>{km(point.distance_m)} · <b>{format(point.elevation_m)} м</b>{point.interpolated?' · інтерполяція':''}</span></div>
    <svg viewBox="0 0 800 135" role="img" aria-label={`Висоти маршруту: від ${low} до ${high} метрів над ареоїдом MOLA`}>
      <defs><linearGradient id="profile-fill" x1="0" y1="0" x2="0" y2="1"><stop stopColor="var(--mc-copper)" stopOpacity=".28"/><stop offset="1" stopColor="var(--mc-copper)" stopOpacity="0"/></linearGradient></defs>
      {[25,65,110].map(v=><line key={v} x1="20" x2="780" y1={v} y2={v} stroke="var(--mc-line)" strokeDasharray="3 6"/>)}
      <polygon points={`20,115 ${line} ${x(profile[profile.length-1].distance_m)},115`} fill="url(#profile-fill)"/>
      <polyline points={line} fill="none" stroke="var(--mc-copper)" strokeWidth="2"/>
      <line x1={x(point.distance_m)} x2={x(point.distance_m)} y1="15" y2="115" stroke="var(--mc-mint)" strokeDasharray="3 4"/>
      <circle cx={x(point.distance_m)} cy={y(point.elevation_m)} r="4" fill="var(--mc-mint)"/>
      <text x="20" y="132" fill="var(--mc-muted)" fontSize="10">A / 0 км</text><text x="780" y="132" textAnchor="end" fill="var(--mc-muted)" fontSize="10">B / {km(total)}</text>
    </svg>
    <input aria-label="Точка профілю висот" type="range" min="0" max={profile.length-1} value={Math.min(index,profile.length-1)} onChange={e=>onIndex(Number(e.target.value))}/>
    <small>Датум: {result.data_quality?.vertical_datum||'MOLA areoid'} · повзунок синхронізований з орбітальним польотом</small>
  </div>
}

export default function MissionControl({onLocal,onDemo,session}:{onLocal:()=>void;onDemo:()=>void;session:RefObject<MissionSnapshot|null>}){
  const saved=session.current
  const [terrain,setTerrain]=useState<GlobalTerrainData|null>(null),[dataError,setDataError]=useState(''),[retry,setRetry]=useState(0)
  const [a,setA]=useState<Fields>(saved?.a??blank),[b,setB]=useState<Fields>(saved?.b??blank),[target,setTarget]=useState<'a'|'b'|'stop'>(saved?.target??'a')
  const [focus,setFocus]=useState<Position|null>(saved?.focus??{lon:-105,lat:15}),[topography,setTopography]=useState(saved?.topography??false),[scale,setScale]=useState(saved?.scale??1)
  // Selection/inspection must not double as an imperative camera command.
  const [inspectionPoint,setInspectionPoint]=useState<Position|null>(focus)
  const [weight,setWeight]=useState(saved?.weight??5),[grade,setGrade]=useState(saved?.grade??15),[result,setResult]=useState<GlobalRoute|null>(saved?.result??null),[alternative,setAlternative]=useState<GlobalRoute|null>(saved?.alternative??null)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[query,setQuery]=useState('')
  const [catalog,setCatalog]=useState<AtlasCatalog|null>(null),[atlasError,setAtlasError]=useState('')
  const [view,setView]=useState<'globe'|'map'>('globe'),[layer,setLayer]=useState('auto'),[geology,setGeology]=useState(false)
  const [stops,setStops]=useState<Position[]>(saved?.stops??[]),[resolution,setResolution]=useState(saved?.resolution??'auto')
  const [units,setUnits]=useState<GeologicalUnit[]>([]),[playing,setPlaying]=useState(false),[flight,setFlight]=useState<number|null>(null)
  const [share,setShare]=useState(''),[copied,setCopied]=useState(false)
  const [sample,setSample]=useState<{elevation_m:number;observations:number|null;interpolated:boolean;dataset:string;spacing_m:number;slope_deg?:number}|null>(null)
  const controller=useRef<AbortController|null>(null),version=useRef(0),sampleVersion=useRef(0)
  const start=position(a),end=position(b)
  useEffect(()=>{session.current={a,b,target,focus,topography,scale,weight,grade,result,alternative,stops,resolution}},[a,b,target,focus,topography,scale,weight,grade,result,alternative,stops,resolution,session])
  useEffect(()=>{
    const abort=new AbortController()
    api<AtlasCatalog>('/api/atlas',{signal:abort.signal}).then(setCatalog).catch(e=>{if(e.name!=='AbortError')setAtlasError(e.message)})
    // Shared plans contain coordinates/parameters only, never a trusted precomputed route.
    const encoded=new URLSearchParams(location.hash.slice(1)).get('mission')
    if(encoded&&!saved){
      try{
        const data=JSON.parse(decodeURIComponent(atob(encoded)))
        const pa=fields(data.start),pb=fields(data.end)
        if(!position(pa)||!position(pb)||!Array.isArray(data.stops)||data.stops.length>4||data.stops.some((p:Position)=>!position(fields(p))))throw Error()
        if(![0,5,20].includes(data.weight)||!Number.isFinite(data.grade)||data.grade<0||data.grade>45)throw Error()
        if(data.resolution&&!['auto','mola','regional','hirise'].includes(data.resolution))throw Error()
        setA(pa);setB(pb);setStops(data.stops.map((p:Position)=>({lon:p.lon,lat:p.lat})));setWeight(data.weight);setGrade(data.grade);setResolution(data.resolution??'auto');setFocus(data.start);setTarget('b')
        setNotice('Спільний план завантажено. Побудуйте маршрут, щоб перевірити його на поточних даних.')
      }catch{setNotice('Посилання містить некоректний план; його не завантажено.')}
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
    api<GlobalTerrainData>('/api/global/terrain',{signal:abort.signal}).then(setTerrain).catch(e=>{if(e.name!=='AbortError')setDataError(e.message)})
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
  function pick(p:Position,navigate=false){
    invalidate()
    if(target==='stop'){
      if(stops.length>=4){setNotice('Максимум чотири проміжні зупинки.');return}
      setStops(prev=>[...prev,{lon:p.lon,lat:p.lat}]);setTarget('b')
    }else{(target==='a'?setA:setB)(fields(p));if(target==='a')setTarget('b')}
    setInspectionPoint(p)
    if(navigate)setFocus(p)
  }
  function showAtlas(){
    document.querySelector('.mc-observatory')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'})
  }
  function demo(){
    invalidate();setStops([]);setA(fields(places[0]));setB(fields({lon:-112.5,lat:-7.5}));setFocus({lon:-122,lat:6});setTarget('b')
  }
  async function build(compare=false){
    if(!start||!end)return
    invalidate();const id=version.current,abort=new AbortController();controller.current=abort;setBusy(true)
    const request=(slope_weight:number)=>api<GlobalRoute>('/api/expedition',{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({start,end,stops,resolution,slope_weight,max_grade_deg:grade})})
    try{
      const primary=await request(weight)
      if(id!==version.current)return
      if(primary.status!=='ok'){
        setResult(primary);setError(primary.message||routeErrors[primary.status])
        return
      }
      setResult(primary)
      if(compare){
        const second=await request(weight===0?20:0)
        if(id!==version.current)return
        if(second.status==='ok')setAlternative(second)
        else setNotice(`Основний маршрут готовий. Альтернатива: ${routeErrors[second.status]}`)
      }
    }catch(e){if(id===version.current&&e instanceof Error&&e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current)setBusy(false)}
  }
  function save(){
    if(!start||!end)return
    try{localStorage.setItem('mars-explorer-mission-v1',JSON.stringify({start,end,weight,grade,stops,resolution}));setNotice('План збережено в цьому браузері.')}
    catch{setNotice('Браузер не дозволив зберегти план.')}
  }
  function restore(){
    try{
      const saved=JSON.parse(localStorage.getItem('mars-explorer-mission-v1')||'null')
      if(!saved)throw Error()
      const a=fields(saved.start),b=fields(saved.end)
      if(!position(a)||!position(b)||![0,5,20].includes(saved.weight)||!Number.isFinite(saved.grade)||saved.grade<0||saved.grade>45)throw Error()
      const restoredStops=saved.stops??[]
      if(!Array.isArray(restoredStops)||restoredStops.length>4||restoredStops.some((p:Position)=>!position(fields(p))))throw Error()
      if(saved.resolution&&!['auto','mola','regional','hirise'].includes(saved.resolution))throw Error()
      invalidate();setStops(restoredStops.map((p:Position)=>({lon:p.lon,lat:p.lat})));setResolution(saved.resolution??'auto');setA(a);setB(b);setTarget('b');setWeight(saved.weight);setGrade(saved.grade);setFocus(saved.start);setNotice('Збережений план відновлено. Побудуйте маршрут.')
    }catch{setNotice('Коректного збереженого плану ще немає.')}
  }
  function download(){
    if(!result?.route)return
    const file={...result.route,properties:{...result.route.properties,metrics:result.metrics,warnings:result.warnings,
      hazard_policy:result.hazard_policy,terrain_validation:result.terrain_validation,fine_terrain_checks:result.terrain_checks,
      profile_sources:result.profile?.map(p=>({dataset:p.dataset??result.dataset,interpolated:p.interpolated}))}}
    const url=URL.createObjectURL(new Blob([JSON.stringify(file,null,2)],{type:'application/geo+json'}))
    const link=document.createElement('a');link.href=url;link.download='mars-global-expedition.geojson';link.click();URL.revokeObjectURL(url)
  }
  const metrics=result?.metrics
  const flightIndex=result?.profile?Math.max(0,result.profile.findIndex(p=>p.distance_m>=(flight??0)*result.profile![result.profile!.length-1].distance_m)):0
  function sharePlan(){
    if(!start||!end)return
    const url=new URL(location.href);url.hash=new URLSearchParams({mission:btoa(encodeURIComponent(JSON.stringify({start,end,stops,weight,grade,resolution})))}).toString()
    setShare(url.toString());setCopied(false)
  }
  return <div className="mission-control">
    <a className="mc-skip" href="#mission-plan">До планування експедиції</a>
    <header className="mc-header">
      <a className="mc-brand" href="/"><span className="mc-brand-symbol"><Planet size={30} weight="regular" aria-hidden/></span><span>MARS<span>EXPLORER</span><small>ЦЕНТР ПЛАНУВАННЯ ЕКСПЕДИЦІЙ</small></span></a>
      <nav aria-label="Режим дослідження"><button className="active" aria-current="page"><GlobeHemisphereWest size={17} aria-hidden/>Планета</button><button onClick={onLocal}><Mountains size={17} aria-hidden/>Jezero · детально</button><a href="#discover">Локації <ArrowUpRight size={15} aria-hidden/></a></nav>
      <div className="mc-system" role="status" data-state={dataError?'error':terrain?'ready':'loading'}><i aria-hidden/>{terrain?'MOLA / ДАНІ ГОТОВІ':dataError?'MOLA / НЕДОСТУПНО':'MOLA / ЗАВАНТАЖЕННЯ'}</div>
    </header>
    <main className="mc-main">
      <section className="mc-intro"><div><div className="mc-kicker"><span><i className="mc-live"/> ПЛАНЕТАРНИЙ АТЛАС</span><span>04 / СОНЯЧНА СИСТЕМА</span></div><h1>Наступний горизонт — <em>Марс.</em></h1><p>Оберіть дві точки. Дослідіть рельєф. Прокладіть власну експедицію.</p><div className="mc-intro-tags"><span><ShieldCheck size={14} aria-hidden/>Числова модель рельєфу</span><span>NASA PDS / USGS</span><span>Дослідницький прототип</span></div></div><div className="mc-planet-facts"><div><strong>144,8<span> млн км²</span></strong><small>ПОВЕРХНЯ ДЛЯ ДОСЛІДЖЕНЬ</small></div><div><strong>463<span> м</span></strong><small>КРОК ПЛАНЕТАРНОЇ DEM</small></div></div></section>
      <div className="mc-workspace">
        <aside className="mc-planner" id="mission-plan">
          <div className="mc-panel-heading"><NavigationArrow size={20} aria-hidden/><h2>Ваша експедиція</h2><span>01 / ПЛАН</span></div>
          <p className="mc-subtle">Від першої точки до нового відкриття.</p>
          <div className="mc-endpoints">
            {([['a','A','Початок',a],['b','B','Кінець',b]] as const).map(([key,letter,label,value])=><div key={key} className={`mc-endpoint ${target===key?'selected':''}`}>
              <button onClick={()=>setTarget(key)} aria-pressed={target===key}><span className={`mc-pin ${key}`}>{letter}</span><strong>{label}</strong><small>{target===key?'ОБЕРІТЬ НА КАРТІ':'ЗМІНИТИ'}</small></button>
              <div className="mc-coordinate-fields">{(['lon','lat'] as const).map(field=><label key={field}>{field==='lon'?'Довгота E':'Широта N'}<input aria-label={`${label}: ${field==='lon'?'довгота':'широта'}`} type="number" step="any" min={field==='lon'?-180:-90} max={field==='lon'?180:90} value={value[field]} placeholder={field==='lon'?'0.0000':'0.0000'} onChange={e=>{invalidate();(key==='a'?setA:setB)(p=>({...p,[field]:e.target.value}))}}/></label>)}</div>
            </div>)}
          </div>
          <div className="mc-inline-actions"><button onClick={()=>{invalidate();setA(b);setB(a);setStops(prev=>[...prev].reverse())}} aria-label="Поміняти A і B"><ArrowsLeftRight size={16} aria-hidden/>Поміняти</button><button onClick={()=>{invalidate();setA(blank());setB(blank());setStops([]);setTarget('a')}}><X size={14} aria-hidden/>Очистити</button></div>
          <div className="mc-stops">
            {stops.map((stop,i)=><div key={i}><span>{i+1}</span><div className="mc-stop-fields">{(['lon','lat'] as const).map(field=><label key={field}>{field==='lon'?'E':'N'}<input aria-label={`Зупинка ${i+1}: ${field==='lon'?'довгота':'широта'}`} type="number" step="any" min={field==='lon'?-180:-90} max={field==='lon'?180:90} value={stop[field]} onChange={e=>{const value=e.target.valueAsNumber;if(!Number.isFinite(value))return;invalidate();setStops(prev=>prev.map((s,j)=>j===i?{...s,[field]:value}:s))}}/></label>)}</div><button aria-label={`Перемістити зупинку ${i+1} вище`} disabled={i===0} onClick={()=>{invalidate();setStops(prev=>{const next=[...prev];[next[i-1],next[i]]=[next[i],next[i-1]];return next})}}>↑</button><button aria-label={`Видалити зупинку ${i+1}`} onClick={()=>{invalidate();setStops(prev=>prev.filter((_,j)=>j!==i))}}><X size={13}/></button></div>)}
            <button className="mc-secondary" disabled={stops.length>=4} aria-pressed={target==='stop'} onClick={()=>setTarget(target==='stop'?'b':'stop')}><Plus size={15} aria-hidden/>{target==='stop'?'Оберіть зупинку на карті':'Додати зупинку'}</button>
          </div>
          <label className="mc-label" htmlFor="global-resolution">МОДЕЛЬ ПОВЕРХНІ</label>
          <select id="global-resolution" value={resolution} onChange={e=>{invalidate();setResolution(e.target.value)}}><option value="auto">Авто · найдетальніша доступна DEM</option><option value="mola">MOLA · глобальний маршрут</option><option value="regional">CTX 20 м · Jezero</option><option value="hirise">HiRISE 1 м · локальна DEM</option></select>
          <label className="mc-label" htmlFor="global-strategy">СТРАТЕГІЯ МАРШРУТУ</label>
          <select id="global-strategy" value={weight} onChange={e=>{invalidate();setWeight(Number(e.target.value))}}><option value="0">Пріоритет відстані</option><option value="5">Збалансована експедиція</option><option value="20">Менші перепади висот</option></select>
          <details className="mc-parameters"><summary>Параметри моделі <span>{grade}°</span></summary><label htmlFor="global-grade">Граничний ухил / градієнт</label><input id="global-grade" type="range" min="0" max="45" value={grade} onChange={e=>{invalidate();setGrade(Number(e.target.value))}}/><p>Абсолютна висота не блокує плавний підйом. Перевіряємо ухили поверхні та переходів; інтерпольовані клітинки мають додатковий штраф. Нерозрізнені каталожні борти захищені окремо. Каміння, ґрунт і зчеплення без вимірювань не оцінюємо.</p></details>
          <button className="mc-primary" onClick={()=>void build()} disabled={!start||!end||!terrain||busy} aria-busy={busy}>{busy?<><CircleNotch className="mc-spinner" size={19} aria-hidden/>Розраховуємо експедицію…</>:<>Побудувати маршрут<ArrowRight size={19} aria-hidden/></>}</button>
          {busy?<button className="mc-secondary" onClick={()=>{invalidate();setNotice('Очікування скасовано. Сервер завершить пошук у межах бюджету.')}}>Скасувати очікування</button>:<button className="mc-secondary" onClick={()=>void build(true)} disabled={!start||!end||!terrain}><Path size={17} aria-hidden/>Порівняти дві стратегії</button>}
           <div className="mc-feedback" role={error?'alert':'status'}>{error||notice||(result?(strategicRoute(result)?'Стратегічний напрямок розрахований. Прохідність не перевірена.':'Шлях у DEM розрахований. Фізична прохідність не підтверджена.'):`Натисніть на карту, щоб встановити ${target==='a'?'початок A':target==='stop'?'проміжну зупинку':'кінець B'}.`)}</div>
          <div className="mc-save"><button onClick={save} disabled={!start||!end}><BookmarkSimple size={15} aria-hidden/>Зберегти</button><button onClick={restore}>Відновити план</button></div>
          <div className="mc-demo"><Sparkle size={18} aria-hidden/><div><strong>Не знаєте, з чого почати?</strong><button onClick={demo}>Експедиція через Tharsis <ArrowRight size={13} aria-hidden/></button></div></div>
           <details className="mc-data-note"><summary><ShieldCheck size={16} aria-hidden/>Наукова модель та обмеження</summary><p>Маршрути: MOLA 463 м уздовж усього шляху (88°S–88°N), у Jezero — CTX 20 м / HiRISE 1 м. Схили й нерозрізнені каталожні борти блокуються. Дно кратера не заборонене; перетин його борту потребує детальнішої DEM. Фото й однакові висоти сусідніх клітинок не доводять прохідність.</p><a href="https://pds-geosciences.wustl.edu/missions/mgs/megdr.html" target="_blank" rel="noreferrer">Походження даних ↗</a></details>
        </aside>
        <section className="mc-observatory" aria-label="Планетарний огляд">
          <div className="mc-map-topline"><div><span className="mc-live"/><span>ОГЛЯД ПЛАНЕТИ <small> / MARS</small></span></div><div className="mc-layer-switch" role="group" aria-label="Режим атласу"><button aria-pressed={view==='globe'} onClick={()=>setView('globe')}><GlobeHemisphereWest size={16} aria-hidden/>Глобус</button><button aria-pressed={view==='map'} onClick={()=>{setPlaying(false);setView('map')}}><MapTrifold size={16} aria-hidden/>2D атлас</button></div></div>
          <div className="mc-atlas-toolbar">
            {view==='globe'?<div className="mc-layer-switch" role="group" aria-label="Вигляд планети"><button aria-pressed={!topography} onClick={()=>setTopography(false)}>Супутник</button><button disabled={!terrain} aria-pressed={topography} onClick={()=>setTopography(true)}>Топографія</button></div>:<label>Підкладка<select aria-label="Картографічний шар" value={layer} onChange={e=>setLayer(e.target.value)}><option value="auto">Авто HD · Viking → CTX → HiRISE</option><option value="viking">Viking · офлайн-мозаїка</option>{catalog?.tiles.map(t=><option key={t.id} value={t.id}>{t.title}</option>)}</select></label>}
            <label className="mc-geology-toggle"><input type="checkbox" checked={geology} onChange={e=>setGeology(e.target.checked)} disabled={!catalog}/>Геологія USGS</label>
            <button className="mc-text" onClick={()=>{setView('map');setFocus({lon:77.4508,lat:18.4447})}}>Jezero · наблизити →</button>
          </div>
           {result&&<div className="mc-traversability" role="status" data-testid="traversability-notice"><strong>{result.terrain_validation?'СХИЛИ ТА БОРТИ: ЧИСЛОВА DEM 463 М':result.hazard_policy?.enabled?'КАТАЛОЖНІ КРАТЕРИ: ОБХІД УВІМКНЕНО':strategicRoute(result)?'ПУНКТИР = НЕПЕРЕВІРЕНИЙ НАПРЯМОК':'ПЕРЕВІРКА ЗА DEM'}</strong><p>{result.message||traversabilityNotice(result)}</p>{(result.terrain_validation||!!result.terrain_checks?.length)&&<><p>Червоне — надмірні схили; помаранчеве — захисна смуга нерозрізненого борту. Обидві області виключені з маршруту. Дно дозволене; для перетину борту потрібна детальніша DEM.</p><button className="mc-secondary" onClick={()=>{setView('map');setFocus(start)}}>Показати схили 463 м та контури</button></>}</div>}
           {view==='globe'?<MarsGlobe start={start} end={end} onPick={pick} onJezero={onLocal} onFallback={()=>setView('map')} terrain={terrain} topography={topography} exaggeration={scale} route={result} focus={focus} mission geology={geology} flightProgress={flight} catalog={catalog}/>:<AtlasMap catalog={catalog} layer={layer} geology={geology} start={start} end={end} stops={stops} route={result} focus={focus} onPick={pick} onLocal={onLocal}/>}
          {topography&&<div className="mc-topography-key"><span>ВИСОТА НАД АРЕОЇДОМ MOLA</span><div><i/><small><span>−8 км</span><span>+21 км</span></small></div><a href="https://pds-geosciences.wustl.edu/missions/mgs/megdr.html" target="_blank" rel="noreferrer">NASA PDS ↗</a></div>}
          <div className="mc-telemetry"><div><span>ВИСОТА · {sample?.dataset?.toUpperCase()??'DEM'} · НАЙКРАЩА ДОСТУПНА</span><strong>{sample?`${format(sample.elevation_m)} м`:'—'}</strong><small>{sample?`${format(sample.spacing_m)} м / клітинка · ${sample.interpolated?'офіційна інтерполяція':sample.observations!==null?`${format(sample.observations)} лазерних спостережень`:'фотограмметрична DEM'}`:'Оберіть місце на карті'}</small></div><label>ПІДСИЛЕННЯ РЕЛЬЄФУ<select aria-label="Підсилення глобального рельєфу" value={scale} onChange={e=>setScale(Number(e.target.value))}><option value="1">×1 · реальний масштаб</option><option value="10">×10 · візуальне підсилення</option></select></label></div>
          {geology&&<div className="mc-geology-info"><span className="mc-chip">USGS SIM 3292 / 1:20M</span><strong>{units.map(u=>u.unit).join(' · ')||'Оберіть точку для геологічного опису'}</strong>{units.map(u=><p key={u.id}><i style={{background:u.color}}/>{u.description}</p>)}<details><summary>Легенда ({catalog?.legend.length??0} одиниць)</summary><div className="mc-geology-legend">{catalog?.legend.map(u=><span key={u.unit}><i style={{background:u.color}}/><b>{u.unit}</b> {u.description}</span>)}</div></details><small>Запит на вихідних полігонах; відображення спрощене. Не карта локальних небезпек.</small></div>}
          {dataError&&<div className="mc-feedback" role="alert">{dataError}<button className="mc-secondary" onClick={()=>setRetry(x=>x+1)}>Повторити завантаження MOLA</button></div>}
          {atlasError&&<div className="mc-feedback" role="alert">Додаткові шари недоступні: {atlasError}</div>}
          <div className="mc-metrics" data-testid={metrics?'global-route-summary':undefined}>
            <div><span>ДОВЖИНА МАРШРУТУ</span><strong>{metrics?km(metrics.distance_m):'—'}<small> A → B</small></strong></div>
            <div><span>НАБІР ВИСОТИ</span><strong>{metrics?`${format(metrics.ascent_m)} м`:'—'}</strong></div>
             <div><span>{result?.terrain_validation?'МАКС. СХИЛ ПОВЕРХНІ DEM · 463 М':strategicRoute(result)?'МАКС. ГРАДІЄНТ КЛІТИНОК MOLA':'МАКС. ГРАДІЄНТ У DEM'}</span><strong>{metrics?`${format(metrics.max_surface_slope_deg??metrics.max_grade_deg,2)}°`:'—'}</strong><small>Не враховує уступів дрібніших за DEM</small></div>
             <div><span>ОБЧИСЛЕННЯ / CPU</span><strong>{busy?'У ПОШУКУ':result?.elapsed_ms!==undefined?`${format(result.elapsed_ms/1000,2)} с`:'ОЧІКУВАННЯ'}</strong><small>{busy?'Перевіряємо переходи DEM':result?.status==='ok'?'Розрахунок завершений':'Оберіть початок і кінець'}</small></div>
          </div>
        </section>
      </div>
      {result?.metrics&&<section className="mc-results">
        <div className="mc-result-heading"><div><span className="mc-kicker">02 / АНАЛІЗ МАРШРУТУ</span><h2>Історія вашої експедиції</h2></div><div className="mc-result-actions"><button className="mc-secondary" onClick={download}><DownloadSimple size={18} aria-hidden/>Експорт GeoJSON</button><button className="mc-secondary" onClick={()=>{downloadReport(result);setNotice('HTML-звіт збережено. Відкрийте його й натисніть «Друк / Зберегти як PDF».')}}><FileText size={18} aria-hidden/>Звіт / PDF</button><button className="mc-secondary" onClick={sharePlan}><ShareNetwork size={18} aria-hidden/>Поділитися / QR</button></div></div>
        <div className="mc-flight-controls"><button className="mc-secondary" disabled={result.route?.geometry.type!=='LineString'} aria-pressed={playing} onClick={()=>{setView('globe');if((flight??0)>=1)setFlight(0);setPlaying(!playing)}}>{playing?<Pause size={17} aria-hidden/>:<Play size={17} aria-hidden/>}{playing?'Призупинити політ':'Політ уздовж маршруту'}</button><button className="mc-text" onClick={()=>{setPlaying(false);setFlight(null);setFocus(start)}}>Скинути огляд</button><span>Орбітальна візуалізація · {Math.round((flight??0)*100)}% · не симуляція руху по ґрунту</span></div>
        <Profile result={result} index={flightIndex} onIndex={i=>{setPlaying(false);setView('globe');const p=result.profile![i];const total=result.profile![result.profile!.length-1].distance_m;setFlight(total?p.distance_m/total:0)}}/>
        <div className="mc-route-notes"><span><Check size={16} aria-hidden/> {format(metrics!.cells)} клітинок · {result.data_quality?.product||result.dataset}</span><span>{metrics!.interpolated_cells} з офіційною інтерполяцією</span><span>Прив’язка точок: {metrics!.snap_offsets_m.map(km).join(' / ')}</span><span>{result.approximate?'Двобічний пошук · точний у коридорі, глобальна оптимальність не гарантована':'Точний A* на локальній DEM-сітці'}</span></div>
        {!!result.legs?.length&&<div className="mc-leg-list">{result.legs.map(l=><div key={l.index}><span>ЕТАП {l.index+1}</span><strong>{km(l.distance_m)}</strong><small>Набір {format(l.ascent_m)} м</small></div>)}</div>}
        {!!result.geological_units?.length&&<details className="mc-route-geology"><summary>Геологія вздовж маршруту · {result.geological_units.length} одиниць</summary>{result.geological_units.map(u=><p key={u.unit}><i style={{background:u.color}}/><b>{u.unit}</b> — {u.description}</p>)}<a href="https://doi.org/10.3133/sim3292" target="_blank" rel="noreferrer">USGS SIM 3292 · вихідні полігони ↗</a></details>}
        {share&&<section className="mc-share" aria-label="Поділитися експедицією"><div><h3>Ваша експедиція. На іншому екрані.</h3><p>Посилання зберігає координати й параметри, не готові розрахунки. На іншому пристрої маршрут потрібно побудувати.</p><input aria-label="Посилання експедиції" readOnly value={share}/><button className="mc-secondary" onClick={()=>{navigator.clipboard?.writeText(share).then(()=>setCopied(true)).catch(()=>setNotice('Скопіюйте посилання з поля вручну.'))}}>{copied?'Скопійовано':'Скопіювати посилання'}</button>{/localhost|127\.0\.0\.1/.test(new URL(share).hostname)&&<p className="mc-share-warning">Це локальна адреса: QR відкриється лише на цьому комп’ютері. Для телефону використайте LAN-адресу в одній Wi-Fi мережі або публічний URL.</p>}</div><img src={assetUrl(`/api/share/qr?url=${encodeURIComponent(share)}`)} alt="QR-код посилання експедиції"/></section>}
        {alternative?.metrics&&<div className="mc-comparison"><h3>Дві стратегії. Ваш вибір.</h3><p>Глобальні варіанти наближені; більший штраф не гарантує меншого набору висоти.</p><div>{[[result,'Поточна стратегія'],[alternative,'Альтернативна стратегія']] .map(([r,title],i)=>{const route=r as GlobalRoute;return <button key={i} onClick={()=>{if(i===1){setPlaying(false);setFlight(null);setResult(alternative);setAlternative(result);setShare('');const selectedWeight=alternative.route?.properties?.slope_weight;if([0,5,20].includes(selectedWeight))setWeight(selectedWeight)}}} aria-pressed={i===0}><span>{String(title)}</span><strong>{km(route.metrics!.distance_m)}</strong><small>Набір {format(route.metrics!.ascent_m)} м · градієнт {format(route.metrics!.max_grade_deg,2)}°</small><b>{i===0?'Відображається':'Показати на глобусі →'}</b></button>})}</div></div>}
      </section>}
      {!!catalog?.missions.length&&<section className="mc-missions"><div className="mc-result-heading"><div><span className="mc-kicker">ОЧИМА ДОСЛІДНИКІВ</span><h2>Реальний Марс. Реальні місії.</h2></div><a href="https://mars.nasa.gov/mars2020/multimedia/raw-images/" target="_blank" rel="noreferrer">Raw Images NASA ↗</a></div><div className="mc-mission-grid">{catalog.missions.map(m=><article key={m.id}><img loading="lazy" src={assetUrl(m.url)} alt={m.title}/><div><span className="mc-kicker">{m.region} / {m.credit}</span><h3>{m.title}</h3><p>{m.description}</p><small>{m.location_note}</small><div><button className="mc-text" onClick={()=>{setFocus({lon:m.lon,lat:m.lat});setView('map');showAtlas()}}>Дослідити регіон →</button><a href={m.source} target="_blank" rel="noreferrer">NASA ↗</a></div></div></article>)}</div></section>}
      <section className="mc-discover" id="discover"><div className="mc-result-heading"><div><span className="mc-kicker">03 / ВІДКРИВАЙТЕ МАРС</span><h2>Місця, що змінюють перспективу.</h2></div><label className="mc-search"><Compass size={18} aria-hidden/><input aria-label="Пошук місць на Марсі" placeholder="Знайти місце…" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
        <p className="mc-subtle">Оберіть місце — встановимо точку {target==='a'?'A':'B'} й повернемо глобус до неї. Координати оглядові.</p>
        <div className="mc-places">{places.filter(p=>`${p.name} ${p.label}`.toLowerCase().includes(query.toLowerCase())).map((p,i)=><button key={p.name} className={`mc-place mc-place-${i%3}`} onClick={()=>{pick(p,true);showAtlas()}}><span>{p.tag}<ArrowRight size={17} aria-hidden/></span><div className="mc-contours" aria-hidden/><strong>{p.name}</strong><small>{p.label}</small><span className="mc-place-coords">{Math.abs(p.lat).toFixed(2)}° {p.lat>=0?'N':'S'} / {Math.abs(p.lon).toFixed(2)}° {p.lon>=0?'E':'W'}</span></button>)}</div>
        {!places.some(p=>`${p.name} ${p.label}`.toLowerCase().includes(query.toLowerCase()))&&<p className="mc-feedback">Місць не знайдено. Спробуйте Olympus, Gale або Jezero.</p>}
      </section>
      <section className="mc-jezero"><div className="mc-jezero-icon"><Mountains size={46} weight="duotone" aria-hidden/></div><div><span className="mc-kicker">НАСТУПНИЙ РІВЕНЬ ДЕТАЛІЗАЦІЇ</span><h2>Наблизьтесь. Jezero чекає.</h2><p>CTX 20 м · локальний HiRISE 1 м · геологія USGS · точний A* на локальній сітці.</p></div><div><button className="mc-primary" onClick={onLocal}>Перейти до Jezero <ArrowRight size={18} aria-hidden/></button><button className="mc-text" onClick={onDemo}>Завантажити демонстраційні точки</button></div></section>
      <footer className="mc-footer"><span>MARS EXPLORER <small> / RESEARCH WITHOUT BORDERS</small></span><span>NASA PDS · USGS · MGS MOLA · VIKING</span><span>Дослідницький прототип / 2026</span></footer>
    </main>
    <nav className="mc-mobile-nav" aria-label="Швидка навігація атласом"><button onClick={showAtlas}><GlobeHemisphereWest size={18} aria-hidden/>Атлас</button><button onClick={()=>document.getElementById('mission-plan')?.scrollIntoView({block:'start'})}><NavigationArrow size={18} aria-hidden/>План</button><button disabled={!result} onClick={()=>document.querySelector('.mc-results')?.scrollIntoView({block:'start'})}><Path size={18} aria-hidden/>Результат</button></nav>
  </div>
}
