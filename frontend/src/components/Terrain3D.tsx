import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { ArrowsOut, ArrowClockwise, ArrowUp, ArrowLeft, ArrowRight } from '@phosphor-icons/react'
import { api, assetUrl } from '../api'
import type { Bundle, Dataset, Position, RouteResult, TerrainMeshData } from '../types'

type Props={
  bundle:Bundle; dataset:Dataset; start:Position|null; end:Position|null; route:RouteResult|null
  visible:Record<string,boolean>; onPick:(p:Position)=>void; onFallback:()=>void
}
type Viewer={camera:THREE.PerspectiveCamera;controls:OrbitControls;render:()=>void;reset:()=>void}
export default function Terrain3D({bundle,dataset,start,end,route,visible,onPick,onFallback}:Props) {
  const host=useRef<HTMLDivElement>(null),shell=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null)
  const callback=useRef(onPick);callback.current=onPick
  const [data,setData]=useState<TerrainMeshData|null>(null),[error,setError]=useState(''),[factor,setFactor]=useState(1)
  const [loading,setLoading]=useState(true)
  const [isFullscreen,setIsFullscreen]=useState(false)
  const savedView=useRef<{dataset:Dataset;position:THREE.Vector3;target:THREE.Vector3}|null>(null)
  const colorMode=visible[`${dataset}-slope`]?'slope':visible[`${dataset}-elevation`]?'height':visible.optical?'optical':'height'
  useEffect(()=>{
    const change=()=>setIsFullscreen(document.fullscreenElement===shell.current)
    document.addEventListener('fullscreenchange',change)
    return ()=>document.removeEventListener('fullscreenchange',change)
  },[])
  useEffect(()=>{
    const abort=new AbortController();setLoading(true);setError('');setData(null)
    api<TerrainMeshData>(`/api/terrain/mesh?dataset=${dataset}&max_size=260`,{signal:abort.signal})
      .then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
      .finally(()=>{if(!abort.signal.aborted)setLoading(false)})
    return ()=>abort.abort()
  },[dataset])
  useEffect(()=>{
    if(!data || data.dataset!==dataset || !host.current)return
    setError('')
    const container=host.current
    let renderer:THREE.WebGLRenderer
    try {renderer=new THREE.WebGLRenderer({antialias:true,alpha:false})}
    catch {setError('WebGL недоступний у цьому браузері. Поверніться до 2D-карти.');return}
    let disposed=false
    const scene=new THREE.Scene();scene.background=new THREE.Color('#151c23')
    renderer.setPixelRatio(Math.min(devicePixelRatio,2))
    renderer.outputColorSpace=THREE.SRGBColorSpace
    renderer.toneMapping=THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure=1.1
    renderer.domElement.setAttribute('aria-label','3D-рельєф Jezero: миша або кнопки для обертання, колесо для масштабу')
    renderer.domElement.setAttribute('tabindex','0')
    container.appendChild(renderer.domElement)
    const geometry=new THREE.BufferGeometry()
    const positions=new Float32Array(data.positions_m)
    for(let i=1;i<positions.length;i+=3)positions[i]*=factor
    const uv=new Float32Array(data.elevations_m.length*2),colors=new Float32Array(data.elevations_m.length*3)
    const optical=dataset==='regional'?bundle.layers.imagery.context:null
    const [[south,west],[north,east]]=optical?.bounds_lat_lon || bundle.layers.imagery.bounds_lat_lon
    const cLow=new THREE.Color(colorMode==='slope'?'#25244b':'#406c78')
    const cHigh=new THREE.Color(colorMode==='slope'?'#ffbe79':'#e8d4ad')
    for(let i=0;i<data.elevations_m.length;i++){
      const row=Math.floor(i/data.shape[1]),col=i%data.shape[1]
      uv[i*2]=(data.longitudes[col]-west)/(east-west)
      uv[i*2+1]=(data.latitudes[row]-south)/(north-south)
      const height=data.elevations_m[i]??data.elevation_origin_m
      const t=colorMode==='slope'?(data.slopes_deg[i]??0)/45:(height-data.elevation_range_m[0])/Math.max(1,data.elevation_range_m[1]-data.elevation_range_m[0])
      const color=cLow.clone().lerp(cHigh,Math.max(0,Math.min(1,t)))
      colors.set([color.r,color.g,color.b],i*3)
    }
    geometry.setAttribute('position',new THREE.BufferAttribute(positions,3))
    geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2))
    geometry.setAttribute('color',new THREE.BufferAttribute(colors,3))
    geometry.setIndex(data.indices);geometry.computeVertexNormals();geometry.computeBoundingBox()
    const span=geometry.boundingBox!.getSize(new THREE.Vector3())
    const size=Math.max(span.x,span.z)
    const material=new THREE.MeshStandardMaterial({color:0xffffff,vertexColors:colorMode!=='optical',roughness:.95,side:THREE.DoubleSide})
    const surface=new THREE.Mesh(geometry,material);scene.add(surface)
    scene.add(new THREE.HemisphereLight('#d8e9ff','#4b382b',2))
    const sun=new THREE.DirectionalLight('#fff3dd',2.4);sun.position.set(-size,size*1.5,size*.4);scene.add(sun)
    const grid=new THREE.GridHelper(size*1.4,14,'#536270','#2a3743');grid.position.y=-size*.015;scene.add(grid)
    const camera=new THREE.PerspectiveCamera(42,1,size/10000,size*15)
    const controls=new OrbitControls(camera,renderer.domElement)
    controls.enableDamping=false;controls.maxPolarAngle=Math.PI*.49
    controls.minDistance=size*.08;controls.maxDistance=size*2.7
    const render=()=>{if(!disposed)renderer.render(scene,camera)}
    const reset=()=>{
      controls.target.set(0,span.y*.3,0)
      camera.position.set(size*.55,size*.85,size*.85)
      controls.update();render()
    }
    let texture:THREE.Texture|null=null
    if(colorMode==='optical'){
      new THREE.TextureLoader().load(assetUrl(optical?.url || '/api/assets/ctx-optical.png'),t=>{
        if(disposed){t.dispose();return}
        texture=t;t.colorSpace=THREE.SRGBColorSpace
        t.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy())
        material.map=t;material.needsUpdate=true;render()
      },undefined,()=>{
        if(!disposed){material.vertexColors=true;material.needsUpdate=true;render();setError('CTX-текстура недоступна; показано реальні висоти кольором.')}
      })
    }
    const toWorld=(p:Position,height:number)=>{
      const rad=Math.PI/180
      return new THREE.Vector3(data.radius_m*(p.lon-data.origin_lon_lat[0])*rad*Math.cos(p.lat*rad),
        (height-data.elevation_origin_m)*factor,
        -data.radius_m*(p.lat-data.origin_lon_lat[1])*rad)
    }
    const nearest=(array:number[],v:number)=>array.reduce((best,x,i)=>Math.abs(x-v)<Math.abs(array[best]-v)?i:best,0)
    const approximateHeight=(p:Position)=>{
      if(p.lon<data.longitudes[0] || p.lon>data.longitudes[data.longitudes.length-1]
        ||p.lat>data.latitudes[0] ||p.lat<data.latitudes[data.latitudes.length-1])return null
      return data.elevations_m[nearest(data.latitudes,p.lat)*data.shape[1]+nearest(data.longitudes,p.lon)]
    }
    const lineResources: {geometry:THREE.BufferGeometry;material:THREE.Material}[]=[]
    if(route?.status==='ok' && route.route){
      const coords=route.route.geometry.type==='LineString'?route.route.geometry.coordinates:
        route.route.geometry.type==='Point'?[route.route.geometry.coordinates]:[]
      const points=coords.map((c,i)=>{
        const height=route.metrics?.elevation_profile[i]?.elevation_m??approximateHeight({lon:c[0],lat:c[1]})??data.elevation_origin_m
        const p=toWorld({lon:c[0],lat:c[1]},height);p.y+=size*.003;return p
      })
      if(points.length>1){
        const path=new THREE.CurvePath<THREE.Vector3>()
        for(let i=1;i<points.length;i++)path.add(new THREE.LineCurve3(points[i-1],points[i]))
        const g=new THREE.TubeGeometry(path,Math.min(points.length*2,2000),size*.0009,5,false)
        const m=new THREE.MeshBasicMaterial({color:'#ffb16f',depthTest:false})
        const line=new THREE.Mesh(g,m);line.renderOrder=10;scene.add(line);lineResources.push({geometry:g,material:m})
      }
    }
    for(const [p,color] of [[start,'#8ed5c7'],[end,'#ffb16f']] as const){
      if(!p)continue
      const height=approximateHeight(p)
      if(height===null)continue
      const g=new THREE.SphereGeometry(size*.009,14,10),m=new THREE.MeshBasicMaterial({color,depthTest:false})
      const point=new THREE.Mesh(g,m);point.position.copy(toWorld(p,height));point.position.y+=size*.005;point.renderOrder=11
      scene.add(point);lineResources.push({geometry:g,material:m})
    }
    const resize=()=>{
      if(disposed)return
      const {width,height}=container.getBoundingClientRect()
      if(!width || !height)return
      renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();render()
    }
    controls.addEventListener('change',render)
    const observer=new ResizeObserver(resize);observer.observe(container)
    const ray=new THREE.Raycaster(),mouse=new THREE.Vector2()
    let down:[number,number]|null=null
    const pointerDown=(e:PointerEvent)=>{down=e.button===0?[e.clientX,e.clientY]:null}
    const pointerUp=(e:PointerEvent)=>{
      if(!down || Math.hypot(e.clientX-down[0],e.clientY-down[1])>5){down=null;return}
      down=null
      const rect=renderer.domElement.getBoundingClientRect()
      mouse.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1)
      ray.setFromCamera(mouse,camera)
      const hit=ray.intersectObject(surface)[0]
      if(hit?.uv)callback.current({lon:west+hit.uv.x*(east-west),lat:south+hit.uv.y*(north-south)})
    }
    renderer.domElement.addEventListener('pointerdown',pointerDown)
    renderer.domElement.addEventListener('pointerup',pointerUp)
    const contextLost=(e:Event)=>{e.preventDefault();setError('WebGL-контекст втрачено. Поверніться до 2D або перезавантажте 3D.')}
    renderer.domElement.addEventListener('webglcontextlost',contextLost)
    viewer.current={camera,controls,render,reset}
    if(savedView.current?.dataset===dataset){
      camera.position.copy(savedView.current.position);controls.target.copy(savedView.current.target);controls.update()
    }else reset()
    resize()
    container.dataset.ready='true'
    return ()=>{
      disposed=true;viewer.current=null;delete container.dataset.ready
      savedView.current={dataset:data.dataset,position:camera.position.clone(),target:controls.target.clone()}
      observer.disconnect();controls.dispose()
      renderer.domElement.removeEventListener('pointerdown',pointerDown)
      renderer.domElement.removeEventListener('pointerup',pointerUp)
      renderer.domElement.removeEventListener('webglcontextlost',contextLost)
      lineResources.forEach(x=>{x.geometry.dispose();x.material.dispose()})
      grid.geometry.dispose();(grid.material as THREE.Material).dispose()
      texture?.dispose();geometry.dispose();material.dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
    }
  },[data,bundle,factor,route,start,end,colorMode,dataset])
  function turn(angle:number){
    const v=viewer.current;if(!v)return
    const offset=v.camera.position.clone().sub(v.controls.target)
    offset.applyAxisAngle(new THREE.Vector3(0,1,0),angle)
    v.camera.position.copy(v.controls.target).add(offset);v.controls.update();v.render()
  }
  function zoom(scale:number){
    const v=viewer.current;if(!v)return
    const offset=v.camera.position.clone().sub(v.controls.target).multiplyScalar(scale)
    v.camera.position.copy(v.controls.target).add(offset);v.controls.update();v.render()
  }
  async function fullscreen(){
    try {if(document.fullscreenElement===shell.current)await document.exitFullscreen();else await shell.current?.requestFullscreen()}
    catch{setError('Повноекранний режим не дозволений браузером.')}
  }
  return <div className="terrain3d-shell" ref={shell}>
    <div ref={host} className="terrain3d-canvas" data-testid="terrain-3d" />
    <div className="terrain3d-title"><span className="live-dot" /> {dataset.toUpperCase()} / 3D DEM · РЕАЛЬНИЙ РЕЛЬЄФ</div>
    <div className="terrain3d-controls">
      <button onClick={()=>turn(-Math.PI/8)} aria-label="Обернути 3D ліворуч"><ArrowLeft size={16} /></button>
      <button onClick={()=>turn(Math.PI/8)} aria-label="Обернути 3D праворуч"><ArrowRight size={16} /></button>
      <button onClick={()=>zoom(.8)} aria-label="Наблизити 3D">+</button>
      <button onClick={()=>zoom(1.25)} aria-label="Віддалити 3D">−</button>
      <button onClick={()=>{const v=viewer.current;if(v){v.camera.position.copy(v.controls.target).add(new THREE.Vector3(0,Math.max(v.controls.getDistance(),1),.01));v.controls.update();v.render()}}}><ArrowUp size={15} aria-hidden />Згори</button>
      <button onClick={()=>viewer.current?.reset()}><ArrowClockwise size={15} aria-hidden />Скинути вид</button>
      <button onClick={fullscreen} aria-pressed={isFullscreen}><ArrowsOut size={15} aria-hidden />{isFullscreen?'Вийти з 3D екрана':'Весь екран'}</button>
    </div>
    <label className="terrain3d-scale">Візуальне підсилення висот
      <select value={factor} onChange={e=>setFactor(Number(e.target.value))}>
        <option value={1}>×1 — метричний масштаб</option><option value={3}>×3 — лише візуалізація</option><option value={8}>×8 — лише візуалізація</option>
      </select>
    </label>
    {loading && <div className="terrain3d-message" role="status">Завантаження справжнього DEM…</div>}
    {error && <div className="terrain3d-message" role="alert">{error}<button onClick={onFallback}>Повернутися до 2D</button></div>}
    <div className="terrain3d-note">
      Обертання — перетягування · масштаб — колесо · панорама — права кнопка · натискання — вибір A/B.
      <br />{factor===1?'Висоти ×1.':`Висоти візуально ×${factor}; A* і профіль не змінено.`}
      {' '}Спрощена модель у межах DEM; NoData — отвори. {dataset==='regional'?'Регіональна текстура зменшена для огляду.':'CTX-текстура 6 м.'} Лінія має візуальний відступ.
    </div>
  </div>
}
