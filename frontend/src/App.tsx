import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Crosshair, DownloadSimple, GlobeHemisphereWest, Mountains, Path, Stack, WarningCircle, SidebarSimple } from '@phosphor-icons/react'
import { api, loadBundle } from './api'
import { MarsMap, geologyColors } from './components/MarsMap'
import { ElevationChart } from './components/ElevationChart'
import type { Bundle, Dataset, Position, Region, RouteResult, Sample } from './types'
import type { MissionSnapshot } from './components/MissionControl'

type Fields = { lon:string; lat:string }
const empty = ():Fields=>({lon:'',lat:''})
function parse(p:Fields):Position|null {
  const lon=Number(p.lon),lat=Number(p.lat)
  return p.lon!=='' && p.lat!=='' && Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lon)<=180 && Math.abs(lat)<=90 ? {lon,lat}:null
}
const messages = {
  no_route:'За обраного порогу ухилу шляху немає. Оберіть інші точки або перегляньте параметри моделі.',
  blocked_endpoint:'Початок або кінець лежить у непрохідній клітинці: NoData, ухил або перепад висот. Оберіть іншу точку.',
  outside_grid:'Одна з точок поза вибраною сіткою. Координати збережено; для маршруту оберіть точки в межах DEM Jezero.',
  search_limit:'Досягнуто ліміту пошуку. Скоротіть маршрут або використайте CTX замість HiRISE.',
}
const number=(n:number,digits=1)=>n.toLocaleString('uk-UA',{maximumFractionDigits:digits})
const Terrain3D=lazy(()=>import('./components/Terrain3D'))
const MissionControl=lazy(()=>import('./components/MissionControl'))

export default function App() {
  const missionSession=useRef<MissionSnapshot|null>(null)
  const [bundle,setBundle]=useState<Bundle|null>(null),[bootError,setBootError]=useState(''),[reload,setReload]=useState(0)
  const [dataset,setDataset]=useState<Dataset>('regional')
  const [a,setA]=useState<Fields>(empty),[b,setB]=useState<Fields>(empty),[target,setTarget]=useState<'start'|'end'>('start')
  const [limit,setLimit]=useState(15),[weight,setWeight]=useState(1)
  const [route,setRoute]=useState<RouteResult|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const [sample,setSample]=useState<Sample|null>(null),[focus,setFocus]=useState<Region|null>(null)
  const [plannerOpen,setPlannerOpen]=useState(true)
  const [showCatalog,setShowCatalog]=useState(false)
  const [viewMode,setViewMode]=useState<'2d'|'3d'|'planet'>('planet')
  const [visible,setVisible]=useState<Record<string,boolean>>({optical:true,science:true})
  const version=useRef(0),controller=useRef<AbortController|null>(null)
  const sampleController=useRef<AbortController|null>(null)
  const sampleVersion=useRef(0)
  const [sampling,setSampling]=useState(false)
  const start=useMemo(()=>parse(a),[a]),end=useMemo(()=>parse(b),[b])
  const bounds=bundle?.layers.terrain[dataset].metadata?.bounds_lon_lat_deg
  const covered=(point:Position|null)=>!point || !!bounds && point.lon>=bounds[0] && point.lon<=bounds[2] && point.lat>=bounds[1] && point.lat<=bounds[3]
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
  function invalidate() {
    version.current++; sampleVersion.current++; controller.current?.abort(); sampleController.current?.abort()
    setSampling(false)
    setBusy(false);setRoute(null);setError('');setFocus(null)
  }
  function chooseTarget(which:'start'|'end') {
    sampleVersion.current++;sampleController.current?.abort();setSampling(false)
    setTarget(which)
  }
  function edit(which:'start'|'end',field:keyof Fields,value:string) {
    invalidate();setSample(null)
    const setter=which==='start'?setA:setB
    setter(prev=>({...prev,[field]:value}))
  }
  async function pick(point:Position) {
    invalidate(); const id=version.current, sampleId=sampleVersion.current, which=target
    setSampling(true)
    sampleController.current=new AbortController()
    try {
      const p=await api<Sample>(`/api/elevation?dataset=${dataset}&lon=${point.lon}&lat=${point.lat}`,{signal:sampleController.current.signal})
      if(id!==version.current || sampleId!==sampleVersion.current)return
      setSample(p)
      if(!p.valid){setError('NoData: ця клітинка не має вимірювань. Точку не вибрано.');return}
      const values={lon:point.lon.toFixed(6),lat:point.lat.toFixed(6)}
      if(which==='start'){setA(values);setTarget('end')} else setB(values)
    }catch(e){if(id===version.current && sampleId===sampleVersion.current && e instanceof Error && e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current && sampleId===sampleVersion.current)setSampling(false)}
  }
  async function build() {
    if(!start || !end){setError('Введіть коректні координати початку й кінця.');return}
    invalidate();const id=version.current
    controller.current=new AbortController();setBusy(true)
    try {
      const result=await api<RouteResult>('/api/route',{method:'POST',signal:controller.current.signal,
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({dataset,start,end,max_slope_deg:limit,slope_weight:weight,nearby_radius_m:200})})
      if(id!==version.current)return
      if(result.status!=='ok'){setError(messages[result.status]);return}
      setRoute(result)
    }catch(e){if(id===version.current && e instanceof Error && e.name!=='AbortError')setError(e.message)}
    finally{if(id===version.current)setBusy(false)}
  }
  function demo() {
    invalidate();setDataset(bundle?.layers.terrain.regional?.available?'regional':'ctx');setLimit(15);setWeight(1);setSample(null)
    setA({lon:'77.450812',lat:'18.444801'});setB({lon:'77.470379',lat:'18.426243'});setTarget('end')
    setViewMode('2d')
  }
  function download() {
    if(!route?.route)return
    const content={...route.route,properties:{...route.route.properties,dataset:route.dataset,
      coordinate_system:'Mars planetocentric/east-positive; NOT WGS84',model_parameters:route.parameters,
      warning:'Research prototype. Not a safety assessment.',metrics:route.metrics}}
    const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/geo+json'}))
    const link=document.createElement('a');link.href=url;link.download='jezero-mars-route.geojson';link.click();URL.revokeObjectURL(url)
  }
  const metrics=route?.metrics
  const science=route?.nearby_science || bundle?.science.features || []
  if(viewMode==='planet')return <Suspense fallback={<div className="panel loading" role="status">Підготовка центру керування експедиціями…</div>}>
    <MissionControl onLocal={()=>setViewMode('2d')} onDemo={demo} session={missionSession}/>
  </Suspense>
  return <div className="app">
    <header className="app-header">
      <a href="/" className="brand" aria-label="Mars Explorer — головна"><GlobeHemisphereWest size={34} weight="duotone" aria-hidden />
        <span>MARS<span className="brand-light">EXPLORER</span><small>INTERPLANETARY SURVIVAL GUIDE</small></span>
      </a>
      <nav aria-label="Навігація"><a href="#planner">Експедиція</a><a href="#science">Наука</a><a href="#sources">Джерела</a></nav>
      <span className="mission-tag"><span className="live-dot" /> JEZERO / MARS</span>
    </header>
    <main>
      <div className="intro flex items-end justify-between gap-4">
        <div><p className="eyebrow">NASA SPACE APPS CHALLENGE 2026 / RESEARCH PROTOTYPE</p>
          <h1>Ближче до поверхні.<br className="mobile-break" /> Глибше в <em>Jezero.</em></h1>
          <p className="intro-copy">Від глобального огляду до деталей: CTX, HiRISE та геологія кратера Jezero.</p>
        </div>
        <div className="coverage-note"><span>ОБЛАСТЬ МАРШРУТИЗАЦІЇ</span><strong>{bundle?.layers.terrain.regional?.available?'≈ 30 × 30 км':'5 × 5 км'}</strong><small>Реальний CTX DEM 20 м · локальний HiRISE 1 м</small></div>
      </div>
      <div className="research-warning"><WarningCircle size={17} aria-hidden /><span>Дослідницька модель, не навігація астронавтів. Розрахований маршрут <strong>не є гарантовано безпечним.</strong></span></div>
      {bootError ? <section className="panel boot-error" role="alert"><h2>Не вдалося отримати дані</h2><p>{bootError}</p>
        <button className="primary" onClick={()=>{setBootError('');setReload(x=>x+1)}}>Спробувати ще раз</button></section>
        :!bundle?<section className="panel loading" role="status">Завантаження наукових шарів Jezero…</section>
        :<>
          <div className="workspace-topline">
            <span>MISSION MAP <span className="workspace-topline-detail">/ уся регіональна карта доступна в «CTX регіон»</span></span>
            <div className="view-mode" role="group" aria-label="Режим відображення">
              <button aria-pressed={false} onClick={()=>setViewMode('planet')}>Планета</button>
              <button aria-pressed={viewMode==='2d'} onClick={()=>setViewMode('2d')}>2D карта</button>
              <button aria-pressed={viewMode==='3d'} onClick={()=>setViewMode('3d')}>3D рельєф</button>
            </div>
            <button className="workspace-toggle" onClick={()=>setPlannerOpen(x=>!x)} aria-expanded={plannerOpen} aria-controls="planner-panel">
              <SidebarSimple size={17} aria-hidden />{plannerOpen?'Карта на всю ширину':'Показати планування'}
            </button>
          </div>
          <div className={`workspace ${plannerOpen?'':'workspace-map-only'}`} id="planner">
            <aside className="planner panel" id="planner-panel" hidden={!plannerOpen}>
              <div className="section-heading"><span className="step">01</span><h2>План експедиції</h2><Path size={22} aria-hidden /></div>
              <label className="field-label" htmlFor="dataset">Модель рельєфу</label>
              <select id="dataset" value={dataset} onChange={e=>{invalidate();setDataset(e.target.value as Dataset);setA(empty());setB(empty());setSample(null);setTarget('start')}}>
                <option value="regional" disabled={!bundle.layers.terrain.regional?.available}>CTX регіон / 20 м · уся карта</option>
                <option value="ctx" disabled={!bundle.layers.terrain.ctx.available}>CTX локально / 20 м · 5 × 5 км</option>
                <option value="hirise" disabled={!bundle.layers.terrain.hirise.available}>HiRISE / 1 м · локальний фрагмент</option>
              </select>
              <details className="terrain-details"><summary>Про покриття й точність DEM</summary><p className="field-hint">{dataset==='regional'
                ?`Сітка ${bundle.layers.terrain.regional.metadata?.shape_rows_cols.join(' × ')}; висоти доступні на ${((bundle.layers.terrain.regional.metadata?.valid_fraction??0)*100).toFixed(1)}% карти. Круті схили можуть блокувати окремий шлях.`
                :dataset==='ctx'?'Локальна сітка 250 × 250. Для довгих маршрутів оберіть CTX регіон.':'Крок по поверхні ≈ 0,949 × 1 м. Окрема детальна локальна сітка.'}</p></details>
              {([['start','A','Початок',a],['end','B','Кінець',b]] as const).map(([which,letter,title,fields])=>
                <div key={which} className={`endpoint ${target===which?'endpoint-active':''}`}>
                  <button className="endpoint-title" onClick={()=>chooseTarget(which)} aria-pressed={target===which}>
                    <span className={`point-badge ${which}`}>{letter}</span><strong>{title}</strong><Crosshair size={18} aria-hidden /><span className="sr-only">Вибрати {title.toLowerCase()} на карті</span>
                  </button>
                  <div className="coordinate-fields">
                    <label>Довгота E<input aria-label={`${title}: довгота`} type="number" step="any" min="-180" max="180" placeholder="77.450812" value={fields.lon} onChange={e=>edit(which,'lon',e.target.value)} /></label>
                    <label>Широта N<input aria-label={`${title}: широта`} type="number" step="any" min="-90" max="90" placeholder="18.444801" value={fields.lat} onChange={e=>edit(which,'lat',e.target.value)} /></label>
                  </div>
                </div>)}
              <button className="text-button" disabled={!start && !end} onClick={()=>{
                invalidate();setSample(null);setA(b);setB(a);setTarget('start')
              }}>Поміняти A ↔ B</button>
              <button className="text-button demo-button" onClick={demo}>Завантажити демонстраційні точки <ArrowRight size={15} aria-hidden /></button>
              <div className="parameter-label"><label htmlFor="slope">Граничний ухил</label><output htmlFor="slope">{limit}°</output></div>
              <input id="slope" type="range" min="0" max="45" step="1" value={limit} onChange={e=>{invalidate();setLimit(Number(e.target.value))}} />
              <div className="range-labels"><span>0°</span><span>Параметр моделі, не ліміт NASA</span><span>45°</span></div>
              <details className="model-details"><summary>Додаткові параметри</summary>
              <label className="field-label" htmlFor="weight">Штраф за схил</label>
              <select id="weight" value={weight} onChange={e=>{invalidate();setWeight(Number(e.target.value))}}>
                <option value="0">Лише відстань</option><option value="1">Збалансований · 1</option><option value="5">Уникати схилів · 5</option>
              </select></details>
              <button className="primary build-button" onClick={build} disabled={!start || !end || busy}>{busy?'Пошук маршруту…':'Build Route'}<ArrowRight size={20} aria-hidden /></button>
              <button className="text-button" onClick={()=>{invalidate();setA(empty());setB(empty());setSample(null);setTarget('start')}}>Очистити план</button>
              <div role={error?'alert':'status'} aria-live="polite" className={`plan-status ${error?'error':''}`}>
                {error || (busy?'A* шукає маршрут по валідних клітинках…':route?'Маршрут розраховано. Точки прив’язані до центрів клітинок.':'Оберіть A та B на карті або введіть координати.')}
              </div>
            </aside>
            <section className="map-column" aria-label="Карта й картографічні шари">
              <div className={`map-interaction panel ${error?'map-interaction-error':''}`}>
                <div className="map-pick-target" role="group" aria-label="Точка для вибору на карті">
                    <button aria-pressed={target==='start'} onClick={()=>chooseTarget('start')}>A · Початок</button>
                    <button aria-pressed={target==='end'} onClick={()=>chooseTarget('end')}>B · Кінець</button>
                  </div><span>{sampling?'Перевіряємо вимірювання DEM…':`Натисніть рельєф, щоб вибрати ${target==='start'?'початок A':'кінець B'}.`}</span>
                {outsideCoverage && <p className="coverage-status" role="status">Точки збережено. Одна або обидві поза DEM {dataset==='regional'?'Jezero':dataset.toUpperCase()}: маршрут по рельєфу тут недоступний.</p>}
                {error && <p role={!plannerOpen?'alert':undefined}>{error}</p>}
                {busy && <div className="map-search-status">
                  <span role="status">A* шукає маршрут…</span>
                  <button className="text-button" onClick={invalidate}>Скасувати очікування</button>
                  <small>Це припинить очікування відповіді; серверний пошук може ще тривати.</small>
                </div>}
              </div>
              {viewMode==='2d'
                ?<MarsMap bundle={bundle} dataset={dataset} start={start} end={end} route={route} visible={visible} focus={focus} onPick={pick} />
                :<Suspense fallback={<div className="panel loading" role="status">Завантаження 3D-модуля…</div>}>
                  <Terrain3D bundle={bundle} dataset={dataset} start={start} end={end} route={route} visible={visible} onPick={pick} onFallback={()=>setViewMode('2d')} />
                </Suspense>}
              <><div className="map-toolbar panel">
                <span className="toolbar-label"><Stack size={18} aria-hidden /> Шари</span>
                {([['optical','CTX оптика'],[`${dataset}-elevation`,'Висоти'],[`${dataset}-slope`,'Ухили'],['geology','Геологія'],['science','Наукові області']] as const).map(([key,label])=>
                  <label className={`layer-chip ${visible[key]?'selected':''}`} key={key}><input type="checkbox" disabled={viewMode==='3d' && (key==='geology'||key==='science')} checked={!!visible[key]} onChange={e=>setVisible(prev=>({...prev,[key]:e.target.checked}))} />{label}</label>)}
                {viewMode==='3d' && <span className="sample-readout">Геологія й наукові полігони доступні в 2D.</span>}
                <span className="sample-readout">{sample?.valid?`${number(sample.elevation_m!)} м / ${number(sample.slope_deg!)}°`:'Натисніть карту для вимірювання'}</span>
              </div>
              <details className="legend panel"><summary>Легенди шарів та обмеження</summary>
                <div className="legend-grid">
                  {(bundle.overlays[dataset]?.overlays || []).map(x=><div key={x.name}>
                    <span>{x.name==='elevation'?'Висоти':'Ухили'} · {x.legend.units}</span>
                    <div className={`color-ramp ${x.name}`} /><small>{number(x.legend.min)} — {number(x.legend.max)} · NoData прозорий</small>
                  </div>)}
                  <div>{bundle.layers.geology.legend.map((g,i)=><p key={g.name}><i style={{background:geologyColors[i%geologyColors.length]}} />{g.name}</p>)}</div>
                </div><p>Межі геології можуть бути зміщені на 100–200 м. Колір ухилів насичується вище 45°. Роздільність не дорівнює точності.</p>
              </details></>
            </section>
          </div>
          <section className="results panel" aria-labelledby="results-heading">
            <div className="section-heading"><span className="step">02</span><h2 id="results-heading">Аналіз маршруту</h2><Mountains size={22} aria-hidden />
              {route && <button className="text-button export-button" onClick={download}><DownloadSimple size={17} aria-hidden />GeoJSON</button>}
            </div>
            {route && metrics ? <>
              <div className="stats-grid" data-testid="route-summary">
                {[['Відстань',`${number(metrics.distance_m)} м`],['Набір / спуск',`+${number(metrics.ascent_m)} / −${number(metrics.descent_m)} м`],
                  ['Висоти',`${number(metrics.min_elevation_m)} … ${number(metrics.max_elevation_m)} м`],
                  ['Макс. ухил поверхні',`${number(metrics.max_slope_deg)}°`]].map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}
              </div>
              <div className="profile-heading"><h3>Профіль висот</h3><span><i className="line-key" /> A* маршрут <i className="line-key steep" /> ділянки для перевірки</span></div>
              <ElevationChart result={route} />
              <p className="field-hint">Поздовжній градієнт до {number(metrics.max_segment_grade_deg)}°. {metrics.steep_segment_indices.length} сегментів досягають 80% обраного порогу й виділені червоним. Вартість A*: {number(route.cost!)}. Набір висоти залежить від роздільності та шуму DEM.</p>
            </>:<div className="empty-results"><Path size={30} aria-hidden /><p>Ваш наступний маршрут починається з двох точок.</p><small>Після пошуку тут з’являться відстань, перепади висот і профіль.</small></div>}
          </section>
          <section id="science" className="science-section">
            <div className="section-heading"><span className="step">03</span><h2>Наука вздовж шляху</h2><span className="count">{science.length} областей</span></div>
            <p className="section-description">{route?'Підтверджені геологічні області, які перетинає маршрут або які лежать у межах 200 проєкційних метрів від нього.':`${bundle.science.features.length} підтверджених областей USGS у розширеному каталозі. Це картовані регіони, а не точкові цілі марсохода; оригінальні назви збережені.`}</p>
            <div className="science-grid" id="science-catalog">{(route||showCatalog?science:science.slice(0,4)).map((region,i)=><article className="science-card panel" key={region.properties.name}>
              <div className="science-number">SCIENCE REGION / {String(i+1).padStart(2,'0')}</div>
              <h3>{region.properties.name}</h3><p>{region.properties.description}</p><p className="interest">{region.properties.research_interest}</p>
              {route && <span className="distance-tag">{region.properties.route_intersects_region?'Маршрут перетинає область':`${number(region.properties.distance_to_route_m!)} м від маршруту`}</span>}
              <div className="science-actions"><button className="text-button" onClick={()=>{
                setFocus(region)
                setViewMode('2d')
                document.getElementById('planner')?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'})
              }}>Показати на карті <ArrowRight size={15} aria-hidden /></button>
                <a href={region.properties.source} target="_blank" rel="noreferrer">USGS ↗</a></div>
            </article>)}</div>
            {!route && science.length>4 && <button className="catalog-toggle" aria-expanded={showCatalog} aria-controls="science-catalog" onClick={()=>setShowCatalog(x=>!x)}>
              {showCatalog?'Згорнути каталог':`Показати всі ${science.length} областей`}
            </button>}
            {!science.length && <p className="panel">Поблизу цього маршруту немає областей з нашого каталогу. Це не означає відсутність наукового інтересу.</p>}
          </section>
          <footer id="sources" className="sources">
            <div><strong>MARS EXPLORER</strong><p>Науковий прототип · Jezero, Mars</p></div>
            <div><h3>Походження даних</h3><a href={bundle.layers.imagery.source} target="_blank" rel="noreferrer">USGS / MRO CTX orthomosaic ↗</a>
              <a href="https://astrogeology.usgs.gov/search/map/mars_2020_science_investigation_ctx_dem_mosaic" target="_blank" rel="noreferrer">CTX DEM · 20 м ↗</a>
              <a href="https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic" target="_blank" rel="noreferrer">HiRISE DTM · 1 м ↗</a>
              <a href={bundle.layers.geology.source} target="_blank" rel="noreferrer">Sun & Stack · USGS SIM 3464 ↗</a>
              <a href="https://astrogeology.usgs.gov/search/map/mars_viking_colorized_global_mosaic_232m" target="_blank" rel="noreferrer">NASA Ames / USGS · Viking global colorized ↗</a></div>
            <div><h3>Наукова відповідальність</h3><p>Координати: Марс, планетоцентрична широта, східна довгота. Не WGS84. Модель не виявляє всі дрібні перешкоди та не сертифікує безпеку.</p></div>
          </footer>
        </>}
    </main>
  </div>
}
