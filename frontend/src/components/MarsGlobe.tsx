import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { ArrowLeft, ArrowRight, ArrowsOut, Crosshair } from '@phosphor-icons/react'
import { api, assetUrl } from '../api'

type Metadata={url:string;title:string;source_page:string;color_note:string}
const jezero={lon:77.4508,lat:18.4447}
function vector(lon:number,lat:number,r=1){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  return new THREE.Vector3(r*Math.cos(b)*Math.cos(a),r*Math.sin(b),-r*Math.cos(b)*Math.sin(a))
}
type Viewer={camera:THREE.PerspectiveCamera;controls:OrbitControls;render:()=>void}

export default function MarsGlobe({onJezero,onFallback,coverageBounds}:{onJezero:()=>void;onFallback:()=>void;coverageBounds?:[number,number,number,number]}){
  const host=useRef<HTMLDivElement>(null),shell=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null)
  const [metadata,setMetadata]=useState<Metadata|null>(null),[error,setError]=useState(''),[loaded,setLoaded]=useState(false)
  const [coordinates,setCoordinates]=useState('Натисніть на Марс, щоб прочитати координати')
  const [fullscreen,setFullscreen]=useState(false)
  useEffect(()=>{
    const abort=new AbortController()
    api<Metadata>('/api/globe',{signal:abort.signal}).then(setMetadata).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return ()=>abort.abort()
  },[])
  useEffect(()=>{
    const change=()=>setFullscreen(document.fullscreenElement===shell.current)
    document.addEventListener('fullscreenchange',change)
    return ()=>document.removeEventListener('fullscreenchange',change)
  },[])
  useEffect(()=>{
    if(!host.current || !metadata)return
    const container=host.current
    let renderer:THREE.WebGLRenderer
    try{renderer=new THREE.WebGLRenderer({antialias:true})}
    catch{setError('WebGL недоступний. Можна відкрити 2D-карту Jezero.');return}
    let disposed=false,texture:THREE.Texture|null=null
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace
    renderer.domElement.setAttribute('aria-label','Глобус Марса: обертайте мишею або кнопками')
    renderer.domElement.tabIndex=0;container.appendChild(renderer.domElement)
    const scene=new THREE.Scene();scene.background=new THREE.Color('#080d14')
    const camera=new THREE.PerspectiveCamera(38,1,.01,50)
    const controls=new OrbitControls(camera,renderer.domElement)
    controls.enablePan=false;controls.enableDamping=false;controls.minDistance=1.16;controls.maxDistance=5
    camera.position.copy(vector(jezero.lon-18,25,3.1));controls.update()
    const material=new THREE.MeshStandardMaterial({color:0xffffff,roughness:1})
    const geometry=new THREE.SphereGeometry(1,128,64)
    const globe=new THREE.Mesh(geometry,material);scene.add(globe)
    scene.add(new THREE.AmbientLight('#ffffff',1.4))
    const sun=new THREE.DirectionalLight('#fff0de',2.1);scene.add(sun)
    const markerGeometry=new THREE.SphereGeometry(.013,14,10)
    const markerMaterial=new THREE.MeshBasicMaterial({color:'#8aefd1'})
    const marker=new THREE.Mesh(markerGeometry,markerMaterial);marker.position.copy(vector(jezero.lon,jezero.lat,1.012));scene.add(marker)
    const borderPoints:THREE.Vector3[]=[]
    // Actual CTX prepared AOI bounds, visible only at close globe zoom.
    const bounds=coverageBounds || [77.40616912514038,18.40279319132929,77.4951012538785,18.487146215619862]
    for(const [lon,lat] of [[bounds[0],bounds[1]],[bounds[2],bounds[1]],[bounds[2],bounds[3]],[bounds[0],bounds[3]],[bounds[0],bounds[1]]])
      borderPoints.push(vector(lon,lat,1.002))
    const borderGeometry=new THREE.BufferGeometry().setFromPoints(borderPoints)
    const borderMaterial=new THREE.LineBasicMaterial({color:'#8aefd1'})
    scene.add(new THREE.Line(borderGeometry,borderMaterial))
    const graticulePositions:number[]=[]
    function line(a:THREE.Vector3,b:THREE.Vector3){graticulePositions.push(...a.toArray(),...b.toArray())}
    for(let lat=-60;lat<=60;lat+=30)for(let lon=-180;lon<180;lon+=3)line(vector(lon,lat,1.001),vector(lon+3,lat,1.001))
    for(let lon=-180;lon<180;lon+=30)for(let lat=-90;lat<90;lat+=3)line(vector(lon,lat,1.001),vector(lon,lat+3,1.001))
    const gridGeometry=new THREE.BufferGeometry()
    gridGeometry.setAttribute('position',new THREE.Float32BufferAttribute(graticulePositions,3))
    const gridMaterial=new THREE.LineBasicMaterial({color:'#d2b99e',transparent:true,opacity:.13})
    scene.add(new THREE.LineSegments(gridGeometry,gridMaterial))
    function render(){
      if(disposed)return
      sun.position.copy(camera.position).add(new THREE.Vector3(-2,2,1))
      renderer.render(scene,camera)
    }
    controls.addEventListener('change',render)
    new THREE.TextureLoader().load(assetUrl(metadata.url),t=>{
      if(disposed){t.dispose();return}
      texture=t;t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy())
      material.map=t;material.needsUpdate=true;container.dataset.ready='true';setLoaded(true);render()
    },undefined,()=>{if(!disposed)setError('Глобальну мозаїку не завантажено. Перевірте підготовку даних.')})
    const resize=()=>{
      if(disposed)return
      const rect=container.getBoundingClientRect()
      if(!rect.width || !rect.height)return
      renderer.setSize(rect.width,rect.height);camera.aspect=rect.width/rect.height;camera.updateProjectionMatrix();render()
    }
    const observer=new ResizeObserver(resize);observer.observe(container)
    const ray=new THREE.Raycaster(),mouse=new THREE.Vector2()
    let down:[number,number]|null=null
    const start=(e:PointerEvent)=>{down=e.button===0?[e.clientX,e.clientY]:null}
    const pick=(e:PointerEvent)=>{
      if(!down || Math.hypot(e.clientX-down[0],e.clientY-down[1])>5){down=null;return}
      down=null
      const rect=renderer.domElement.getBoundingClientRect()
      mouse.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1)
      ray.setFromCamera(mouse,camera)
      const hit=ray.intersectObject(globe)[0]
      if(hit){
        const p=hit.point.clone().normalize()
        const lat=Math.asin(THREE.MathUtils.clamp(p.y,-1,1))*180/Math.PI
        const lon=Math.atan2(-p.z,p.x)*180/Math.PI
        setCoordinates(`${Math.abs(lat).toFixed(2)}° ${lat>=0?'N':'S'} / ${Math.abs(lon).toFixed(2)}° ${lon>=0?'E':'W'} · лише глобальний огляд`)
      }
    }
    renderer.domElement.addEventListener('pointerdown',start);renderer.domElement.addEventListener('pointerup',pick)
    const contextLost=(e:Event)=>{e.preventDefault();setError('WebGL-контекст втрачено. Поверніться до 2D.')}
    renderer.domElement.addEventListener('webglcontextlost',contextLost)
    viewer.current={camera,controls,render};resize()
    return ()=>{
      disposed=true;viewer.current=null;delete container.dataset.ready
      observer.disconnect();controls.dispose()
      renderer.domElement.removeEventListener('pointerdown',start);renderer.domElement.removeEventListener('pointerup',pick)
      renderer.domElement.removeEventListener('webglcontextlost',contextLost)
      geometry.dispose();material.dispose();texture?.dispose();markerGeometry.dispose();markerMaterial.dispose()
      borderGeometry.dispose();borderMaterial.dispose();gridGeometry.dispose();gridMaterial.dispose()
      renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
    }
  },[metadata,coverageBounds])
  function rotate(angle:number){
    const v=viewer.current;if(!v)return
    v.camera.position.applyAxisAngle(new THREE.Vector3(0,1,0),angle);v.controls.update();v.render()
  }
  function zoom(scale:number){
    const v=viewer.current;if(!v)return
    v.camera.position.multiplyScalar(scale);v.controls.update();v.render()
  }
  function showJezero(){
    const v=viewer.current;if(!v)return
    v.camera.position.copy(vector(jezero.lon,jezero.lat,2.7));v.controls.target.set(0,0,0);v.controls.update();v.render()
  }
  async function toggleFullscreen(){
    try{if(document.fullscreenElement===shell.current)await document.exitFullscreen();else await shell.current?.requestFullscreen()}
    catch{setError('Повноекранний режим не дозволений браузером.')}
  }
  return <div className="globe-shell" ref={shell}>
    <div ref={host} className="globe-canvas" data-testid="mars-globe" />
    <div className="globe-title"><span className="live-dot" /> MARS / ВСЯ ПЛАНЕТА <small>VIKING · MDIM 2.1</small></div>
    <div className="globe-controls">
      <button onClick={()=>rotate(-Math.PI/6)} aria-label="Обернути Марс ліворуч"><ArrowLeft size={16}/></button>
      <button onClick={()=>rotate(Math.PI/6)} aria-label="Обернути Марс праворуч"><ArrowRight size={16}/></button>
      <button onClick={()=>zoom(.8)} aria-label="Наблизити планету">+</button>
      <button onClick={()=>zoom(1.25)} aria-label="Віддалити планету">−</button>
      <button onClick={showJezero}><Crosshair size={15} aria-hidden/>Показати Jezero</button>
      <button onClick={toggleFullscreen} aria-pressed={fullscreen}><ArrowsOut size={15} aria-hidden/>{fullscreen?'Вийти з глобуса':'Весь екран'}</button>
    </div>
    <div className="globe-destination">
      <span className="eyebrow">ПІДГОТОВЛЕНИЙ РАЙОН ЕКСПЕДИЦІЇ</span><h3>Jezero Crater</h3>
      <p>18.4447° N / 77.4508° E<br/>{coverageBounds?'CTX DEM ≈ 30 × 30 км':'CTX DEM'} · локальний HiRISE · геологія</p>
      <button className="primary" onClick={onJezero}>Перейти до Jezero →</button>
      <small>Зелений маркер перебільшено для видимості; це не розмір кратера.</small>
    </div>
    {!loaded && !error && <div className="terrain3d-message" role="status">Завантаження глобальної мозаїки Марса…</div>}
    {error && <div className="terrain3d-message" role="alert">{error}<button onClick={onFallback}>До 2D карти</button></div>}
    <div className="globe-note"><strong>{coordinates}</strong><br/>
      Реальна Viking-мозаїка, офіційно колоризована NASA Ames/USGS — не true-color фото.
      Сферичний огляд без глобального DEM. Детальні маршрути — тільки Jezero.
      {metadata && <a href={metadata.source_page} target="_blank" rel="noreferrer"> Першоджерело ↗</a>}
    </div>
  </div>
}
