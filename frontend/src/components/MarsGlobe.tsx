import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { ArrowLeft, ArrowRight, ArrowsOut, Crosshair } from '@phosphor-icons/react'
import { api, assetUrl } from '../api'
import type { Position, GlobalTerrainData, GlobalRoute, AtlasCatalog } from '../types'
import { globeImagery } from './globeImagery'
import type { DetailStatus } from './globeImagery'
import { strategicRoute } from './routeAssessment'
import { craterRing } from './hazardGeometry'
import { globeSurface,surfaceLineMaterial } from './globeSurface'
import { routeAnchors } from './routeAnchors'

type Metadata={url:string;title:string;source_page:string;color_note:string}
const jezero={lon:77.4508,lat:18.4447}
function vector(lon:number,lat:number,r=1){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  return new THREE.Vector3(r*Math.cos(b)*Math.cos(a),r*Math.sin(b),-r*Math.cos(b)*Math.sin(a))
}
type Viewer={camera:THREE.PerspectiveCamera;controls:OrbitControls;render:()=>void;framingDistance:number;updateSurface:()=>void;fly:(progress:number)=>void;zoomBy:(scale:number)=>void;detail:()=>void}

export default function MarsGlobe({onJezero,onFallback,coverageBounds,start,end,onPick,terrain,topography=false,exaggeration=1,route,focus,mission=false,geology=false,flightProgress=null,catalog}:{onJezero:()=>void;onFallback:()=>void;coverageBounds?:[number,number,number,number];start:Position|null;end:Position|null;onPick:(point:Position)=>void;terrain?:GlobalTerrainData|null;topography?:boolean;exaggeration?:number;route?:GlobalRoute|null;focus?:Position|null;mission?:boolean;geology?:boolean;flightProgress?:number|null;catalog?:AtlasCatalog|null}){
  const host=useRef<HTMLDivElement>(null),shell=useRef<HTMLDivElement>(null),viewer=useRef<Viewer|null>(null)
  const callback=useRef(onPick);callback.current=onPick
  const endpoints=useRef([start,end]);endpoints.current=[start,end]
  const surface=useRef({terrain,topography,exaggeration,route,geology});surface.current={terrain,topography,exaggeration,route,geology}
  const imageryState=useRef({catalog,topography});imageryState.current={catalog,topography}
  const [detail,setDetail]=useState<DetailStatus|null>(null)
  const [metadata,setMetadata]=useState<Metadata|null>(null),[error,setError]=useState(''),[loaded,setLoaded]=useState(false)
  const [coordinates,setCoordinates]=useState('Натисніть на Марс, щоб розмістити A або B')
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
    let disposed=false,texture:THREE.Texture|null=null,topoTexture:THREE.Texture|null=null,topoLoading=false
    let geologicalTexture:THREE.Texture|null=null,geologicalLoading=false
    let imagery:ReturnType<typeof globeImagery>|null=null
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace
    renderer.domElement.setAttribute('aria-label','Глобус Марса: обертайте мишею або кнопками')
    renderer.domElement.tabIndex=0;container.appendChild(renderer.domElement)
    const scene=new THREE.Scene();scene.background=new THREE.Color('#080c12')
    const camera=new THREE.PerspectiveCamera(38,1,.01,50)
    const controls=new OrbitControls(camera,renderer.domElement)
    controls.enablePan=false;controls.enableZoom=false;controls.enableDamping=false;controls.minDistance=1.16;controls.maxDistance=5
    camera.position.copy(vector(jezero.lon-18,25,3.1));controls.update()
    const material=new THREE.MeshStandardMaterial({color:0xffffff,roughness:1})
    const geometry=new THREE.SphereGeometry(1,360,180)
    const globe=new THREE.Mesh(geometry,material);scene.add(globe)
    const drape=globeSurface(globe)
    const geologyMaterial=new THREE.MeshBasicMaterial({transparent:true,opacity:.57,depthWrite:false})
    const geologyMesh=new THREE.Mesh(geometry,geologyMaterial);geologyMesh.scale.setScalar(1.0006);geologyMesh.visible=false;scene.add(geologyMesh)
    scene.add(new THREE.AmbientLight('#ffffff',1.4))
    const sun=new THREE.DirectionalLight('#fff0de',2.1);scene.add(sun)
    // Static, deterministic star field. Rendering remains demand-driven.
    const starPositions:number[]=[]
    for(let i=0;i<700;i++){
      const z=1-2*(i+.5)/700,angle=i*2.3999632297,rad=Math.sqrt(1-z*z)
      starPositions.push(14*rad*Math.cos(angle),14*z,14*rad*Math.sin(angle))
    }
    const starsGeometry=new THREE.BufferGeometry()
    starsGeometry.setAttribute('position',new THREE.Float32BufferAttribute(starPositions,3))
    const starsMaterial=new THREE.PointsMaterial({color:'#aabbd0',size:.018,transparent:true,opacity:.6})
    scene.add(new THREE.Points(starsGeometry,starsMaterial))
    const routeGeometry=new THREE.BufferGeometry()
    const routeMaterial=surfaceLineMaterial(new THREE.LineBasicMaterial({color:'#94f0d0',depthTest:true}))
    const strategicMaterial=surfaceLineMaterial(new THREE.LineDashedMaterial({color:'#f0b180',dashSize:.01,gapSize:.007,depthTest:true}))
    const routeLine=new THREE.Line(routeGeometry,routeMaterial);scene.add(routeLine)
    const snapGeometry=new THREE.BufferGeometry()
    const snapMaterial=surfaceLineMaterial(new THREE.LineBasicMaterial({color:'#c1c8cf',transparent:true,opacity:.65}))
    const snapLines=new THREE.LineSegments(snapGeometry,snapMaterial);scene.add(snapLines)
    const hazardGeometry=new THREE.BufferGeometry()
    const hazardMaterial=surfaceLineMaterial(new THREE.LineBasicMaterial({color:'#ff7676',transparent:true,opacity:.8}))
    const hazardLines=new THREE.LineSegments(hazardGeometry,hazardMaterial);scene.add(hazardLines)
    function elevationAt(lon:number,lat:number){
      const data=surface.current.terrain;if(!data)return 0
      const row=Math.max(0,Math.min(data.shape[0]-1,Math.round((data.latitudes[0]-lat)/(180/data.shape[0]))))
      const col=((Math.round((((lon%360)+360)%360-data.longitudes[0])/(360/data.shape[1]))%data.shape[1])+data.shape[1])%data.shape[1]
      return data.elevations_m[row*data.shape[1]+col]
    }
    function radiusAt(lon:number,lat:number){
      return 1+elevationAt(lon,lat)*(surface.current.exaggeration)/(surface.current.terrain?.radius_m||3396000)
    }
    function updateSurface(){
      const positions=geometry.getAttribute('position')
      const direction=new THREE.Vector3()
      for(let i=0;i<positions.count;i++){
        direction.fromBufferAttribute(positions,i).normalize()
        const lat=Math.asin(THREE.MathUtils.clamp(direction.y,-1,1))*180/Math.PI
        const lon=Math.atan2(-direction.z,direction.x)*180/Math.PI
        direction.multiplyScalar(radiusAt(lon,lat));positions.setXYZ(i,direction.x,direction.y,direction.z)
      }
      positions.needsUpdate=true;geometry.computeVertexNormals();geometry.computeBoundingSphere()
      const data=surface.current.terrain
      if(data && !topoTexture && !topoLoading){
        topoLoading=true
        new THREE.TextureLoader().load(assetUrl(data.texture_url),t=>{
          if(disposed){t.dispose();return}
          topoTexture=t;t.colorSpace=THREE.SRGBColorSpace;updateSurface()
        },undefined,()=>{if(!disposed){topoLoading=false;setError('Не вдалося завантажити топографічну текстуру.')}})
      }
      material.map=surface.current.topography && topoTexture?topoTexture:texture;material.needsUpdate=true
      if(surface.current.geology&&!geologicalTexture&&!geologicalLoading){
        geologicalLoading=true
        new THREE.TextureLoader().load(assetUrl('/api/assets/global-geology.png'),t=>{
          if(disposed){t.dispose();return}
          geologicalTexture=t;t.colorSpace=THREE.SRGBColorSpace
          geologyMaterial.map=t;geologyMaterial.needsUpdate=true;updateSurface()
        },undefined,()=>{if(!disposed){geologicalLoading=false;setError('Геологічний шар недоступний.')}})
      }
      geologyMesh.visible=surface.current.geology&&!!geologicalTexture
      const g=surface.current.route?.route?.geometry
      const points=g?.type==='LineString'?g.coordinates:g?.type==='Point'?[g.coordinates]:[]
      const linePoints=drape.path(points)
      routeGeometry.setAttribute('position',new THREE.Float32BufferAttribute(linePoints.flatMap(p=>p.toArray()),3))
      routeGeometry.setDrawRange(0,linePoints.length)
      if(linePoints.length)routeGeometry.computeBoundingSphere()
      routeLine.material=strategicRoute(surface.current.route)?strategicMaterial:routeMaterial
      if(linePoints.length)routeLine.computeLineDistances()
      routeLine.visible=linePoints.length>1;render()
      const snapPoints:number[]=[]
      routeAnchors(surface.current.route,endpoints.current).forEach(anchor=>{
        if(anchor.offsetM<=.5)return
        const line=drape.path([[anchor.actual.lon,anchor.actual.lat],[anchor.snapped.lon,anchor.snapped.lat]])
        line.slice(1).forEach((p,i)=>snapPoints.push(...line[i].toArray(),...p.toArray()))
      })
      snapGeometry.setAttribute('position',new THREE.Float32BufferAttribute(snapPoints,3))
      snapGeometry.setDrawRange(0,snapPoints.length/3)
      if(snapPoints.length)snapGeometry.computeBoundingSphere()
      snapLines.visible=snapPoints.length>0
      const hazardPoints:number[]=[]
      surface.current.route?.hazards?.forEach(crater=>{
        const ring=craterRing(crater)
        ring.slice(1).forEach((p,i)=>{
          const a=ring[i]
          hazardPoints.push(...drape.point(a.lon,a.lat).toArray(),...drape.point(p.lon,p.lat).toArray())
        })
      })
      hazardGeometry.setAttribute('position',new THREE.Float32BufferAttribute(hazardPoints,3))
      hazardGeometry.setDrawRange(0,hazardPoints.length/3)
      if(hazardPoints.length)hazardGeometry.computeBoundingSphere()
      hazardLines.visible=hazardPoints.length>0;render()
    }
    const markerGeometry=new THREE.SphereGeometry(.013,14,10)
    const markerMaterial=new THREE.MeshBasicMaterial({color:'#8aefd1'})
    const marker=new THREE.Mesh(markerGeometry,markerMaterial);marker.position.copy(vector(jezero.lon,jezero.lat,1.012));scene.add(marker)
    const pins=['A','B'].map((label,i)=>{
      const canvas=document.createElement('canvas');canvas.width=96;canvas.height=96
      const ctx=canvas.getContext('2d')!
      ctx.beginPath();ctx.arc(48,48,38,0,Math.PI*2);ctx.fillStyle=i===0?'#8ed5c7':'#f5b079';ctx.fill()
      ctx.lineWidth=5;ctx.strokeStyle='#172027';ctx.stroke()
      ctx.fillStyle='#172027';ctx.font='bold 44px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(label,48,49)
      const map=new THREE.CanvasTexture(canvas);map.colorSpace=THREE.SRGBColorSpace
      const pin=new THREE.Sprite(new THREE.SpriteMaterial({map,depthTest:false,depthWrite:false,sizeAttenuation:false}))
      pin.renderOrder=10
      pin.scale.set(.036,.036,1);scene.add(pin);return pin
    })
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
      // OrbitControls uses a fixed angle per pixel, ignoring perspective zoom.
      // Match rotation to the visible surface span instead (roughly 1:1 drag).
      controls.rotateSpeed=Math.min(1,Math.max(.0000001,
        (camera.position.length()-1)*Math.tan(camera.fov*Math.PI/360)/(Math.PI*camera.zoom)))
      const direction=camera.position.clone().normalize()
      container.dataset.viewLon=String(Math.atan2(-direction.z,direction.x)*180/Math.PI)
      container.dataset.viewLat=String(Math.asin(direction.y)*180/Math.PI)
      container.dataset.cameraZoom=String(camera.zoom)
      const dash=Math.max(.0000001,(camera.position.length()-1)*Math.tan(camera.fov*Math.PI/360)/camera.zoom/25)
      strategicMaterial.dashSize=dash;strategicMaterial.gapSize=dash*.7
      pins.forEach((pin,i)=>{
        const p=endpoints.current[i];pin.visible=!!p
        // Sprite sizeAttenuation=false still includes perspective camera.zoom.
        // Keep markers screen-sized rather than covering the terrain at HD zoom.
        pin.scale.set(.036/camera.zoom,.036/camera.zoom,1)
        if(p){
          pin.position.copy(drape.point(p.lon,p.lat))
          pin.visible=camera.position.clone().sub(pin.position).dot(pin.position)>0
        }
      })
      sun.position.copy(camera.position).add(new THREE.Vector3(-2,2,1))
      renderer.render(scene,camera)
    }
    function fly(progress:number){
      const g=surface.current.route?.route?.geometry
      if(g?.type!=='LineString'||g.coordinates.length<2)return
      const profile=surface.current.route?.profile
      const total=profile?.[profile.length-1].distance_m||1
      const destination=Math.max(0,Math.min(1,progress))*total
      let index=0
      if(profile)while(index<profile.length-2&&profile[index+1].distance_m<destination)index++
      else index=Math.min(g.coordinates.length-2,Math.floor(progress*(g.coordinates.length-1)))
      const a=g.coordinates[index],b=g.coordinates[index+1]
      const mix=profile?Math.max(0,Math.min(1,(destination-profile[index].distance_m)/Math.max(.001,profile[index+1].distance_m-profile[index].distance_m))):0
      const v=vector(a[0],a[1]).lerp(vector(b[0],b[1]),mix).normalize()
      camera.zoom=1;camera.updateProjectionMatrix()
      controls.target.set(0,0,0);camera.position.copy(v.multiplyScalar(1.8));controls.update();render()
    }
    function zoomBy(scale:number){
      if(camera.zoom>1||camera.position.length()*scale<controls.minDistance){
        const remaining=camera.position.length()*scale/controls.minDistance
        if(camera.zoom===1)camera.position.setLength(controls.minDistance)
        camera.zoom=Math.max(1,Math.min(8192,camera.zoom/(camera.zoom>1?scale:remaining)))
        camera.updateProjectionMatrix()
      }else camera.position.setLength(Math.min(controls.maxDistance,camera.position.length()*scale))
      controls.update();render();imagery?.schedule()
    }
    imagery=globeImagery(material,camera,renderer,()=>imageryState.current,render,setDetail)
    imagery.schedule()
    const changed=()=>{render();imagery?.schedule()}
    controls.addEventListener('change',changed)
    const wheel=(e:WheelEvent)=>{e.preventDefault();zoomBy(Math.exp(Math.max(-150,Math.min(150,e.deltaY))*.002))}
    renderer.domElement.addEventListener('wheel',wheel,{passive:false})
    new THREE.TextureLoader().load(assetUrl(metadata.url),t=>{
      if(disposed){t.dispose();return}
      texture=t;t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=Math.min(4,renderer.capabilities.getMaxAnisotropy())
      material.map=t;material.needsUpdate=true;container.dataset.ready='true';setLoaded(true);updateSurface();imagery?.schedule()
    },undefined,()=>{if(!disposed)setError('Глобальну мозаїку не завантажено. Перевірте підготовку даних.')})
    let previousFraming:number|null=null
    const resize=()=>{
      if(disposed)return
      const rect=container.getBoundingClientRect()
      if(!rect.width || !rect.height)return
      renderer.setSize(rect.width,rect.height);camera.aspect=rect.width/rect.height
      // Fit a complete sphere on portrait screens, preserving relative user zoom.
      const halfFov=Math.atan(Math.tan(camera.fov*Math.PI/360)*Math.min(1,camera.aspect))
      const framing=1.08/Math.sin(halfFov)
      controls.maxDistance=Math.max(5,framing*1.5)
      camera.position.setLength(previousFraming?camera.position.length()*framing/previousFraming:framing)
      previousFraming=framing
      if(viewer.current)viewer.current.framingDistance=framing
      camera.updateProjectionMatrix();controls.update();render();imagery?.schedule()
    }
    const observer=new ResizeObserver(resize);observer.observe(container)
    const ray=new THREE.Raycaster(),mouse=new THREE.Vector2()
    let down:[number,number]|null=null,pinchDistance=0,dragFrame=0
    const pointers=new Map<number,[number,number]>()
    const start=(e:PointerEvent)=>{
      pointers.set(e.pointerId,[e.clientX,e.clientY])
      down=e.button===0&&e.isPrimary&&pointers.size===1?[e.clientX,e.clientY]:null
      if(pointers.size===2){const [a,b]=[...pointers.values()];pinchDistance=Math.hypot(a[0]-b[0],a[1]-b[1]);down=null}
    }
    const move=(e:PointerEvent)=>{
      if(pointers.has(e.pointerId)){
        pointers.set(e.pointerId,[e.clientX,e.clientY])
        // Tiny rotations can be below OrbitControls' fixed change-event epsilon.
        // Draw after its pointer handler, without a permanent animation loop.
        if(!dragFrame)dragFrame=requestAnimationFrame(()=>{
          dragFrame=0;render();imagery?.schedule()
        })
      }
      if(pointers.size===2){
        const [a,b]=[...pointers.values()],distance=Math.hypot(a[0]-b[0],a[1]-b[1])
        if(pinchDistance>0&&distance>0)zoomBy(pinchDistance/distance)
        pinchDistance=distance;down=null
      }
      if(down&&Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)down=null
    }
    const cancel=(e:PointerEvent)=>{pointers.delete(e.pointerId);pinchDistance=0;down=null}
    const pick=(e:PointerEvent)=>{
      pointers.delete(e.pointerId);pinchDistance=0
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
        setCoordinates(`${Math.abs(lat).toFixed(4)}° ${lat>=0?'N':'S'} / ${Math.abs(lon).toFixed(4)}° ${lon>=0?'E':'W'}`)
        callback.current({lon,lat})
      }
    }
    renderer.domElement.addEventListener('pointerdown',start);renderer.domElement.addEventListener('pointerup',pick)
    renderer.domElement.addEventListener('pointermove',move);renderer.domElement.addEventListener('pointercancel',cancel)
    const contextLost=(e:Event)=>{e.preventDefault();setError('WebGL-контекст втрачено. Поверніться до 2D.')}
    renderer.domElement.addEventListener('webglcontextlost',contextLost)
    viewer.current={camera,controls,render,framingDistance:3.1,updateSurface,fly,zoomBy,detail:()=>imagery?.schedule()};resize();updateSurface()
    return ()=>{
      disposed=true;viewer.current=null;delete container.dataset.ready
      observer.disconnect();controls.removeEventListener('change',changed);controls.dispose();imagery?.dispose()
      cancelAnimationFrame(dragFrame)
      renderer.domElement.removeEventListener('wheel',wheel)
      renderer.domElement.removeEventListener('pointerdown',start);renderer.domElement.removeEventListener('pointerup',pick)
      renderer.domElement.removeEventListener('pointermove',move);renderer.domElement.removeEventListener('pointercancel',cancel)
      renderer.domElement.removeEventListener('webglcontextlost',contextLost)
      geometry.dispose();material.dispose();texture?.dispose();markerGeometry.dispose();markerMaterial.dispose()
      pins.forEach(pin=>{pin.material.map?.dispose();pin.material.dispose()})
      borderGeometry.dispose();borderMaterial.dispose();gridGeometry.dispose();gridMaterial.dispose()
      routeGeometry.dispose();routeMaterial.dispose();strategicMaterial.dispose();starsGeometry.dispose();starsMaterial.dispose();topoTexture?.dispose()
      hazardGeometry.dispose();hazardMaterial.dispose()
      snapGeometry.dispose();snapMaterial.dispose()
      geologyMaterial.dispose();geologicalTexture?.dispose()
      renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove()
    }
  },[metadata,coverageBounds])
  useEffect(()=>{viewer.current?.render()},[start,end])
  useEffect(()=>{viewer.current?.updateSurface()},[terrain,topography,exaggeration,route,geology])
  useEffect(()=>{viewer.current?.detail()},[catalog,topography])
  useEffect(()=>{if(flightProgress!==null)viewer.current?.fly(flightProgress)},[flightProgress,loaded])
  useEffect(()=>{
    const v=viewer.current;if(!v||!focus)return
    v.camera.zoom=1;v.camera.updateProjectionMatrix()
    v.camera.position.copy(vector(focus.lon,focus.lat,v.framingDistance));v.controls.update();v.render();v.detail()
  },[focus,loaded])
  function rotate(angle:number){
    const v=viewer.current;if(!v)return
    v.camera.position.applyAxisAngle(new THREE.Vector3(0,1,0),angle*Math.min(1,1/v.camera.zoom));v.controls.update();v.render()
  }
  function zoom(scale:number){
    const v=viewer.current;if(!v)return
    v.zoomBy(scale)
  }
  function showJezero(){
    const v=viewer.current;if(!v)return
    v.camera.zoom=1;v.camera.updateProjectionMatrix()
    v.camera.position.copy(vector(jezero.lon,jezero.lat,v.framingDistance));v.controls.target.set(0,0,0);v.controls.update();v.render()
  }
  async function toggleFullscreen(){
    try{if(document.fullscreenElement===shell.current)await document.exitFullscreen();else await shell.current?.requestFullscreen()}
    catch{setError('Повноекранний режим не дозволений браузером.')}
  }
  return <div className="globe-shell" ref={shell}>
    <div ref={host} className="globe-canvas" data-testid="mars-globe" data-detail-source={detail?.source} data-detail-zoom={detail?.zoom} data-detail-ready={detail?.ready} data-detail-total={detail?.total} data-detail-fallback={detail?.fallback}/>
    {detail&&<div className="globe-detail-status" role="status"><strong>{detail.source}</strong><span>LOD {detail.zoom} · {detail.ready}/{detail.total} тайлів · ≈{detail.spacing.toFixed(1)} м/пікс. по довготі{detail.preview&&detail.ready<detail.total?' · огляд уже завантажений, деталізація уточнюється':''}{detail.fallback?` · ${detail.fallback} тайлів нижчого LOD`:''}{detail.limited?' · межа джерела':''}{detail.offline?' · частина даних недоступна, збережено підкладку':''}</span></div>}
    <div className="globe-title"><span className="live-dot" /> MARS / ВСЯ ПЛАНЕТА <small>{topography?'MOLA · TOPOGRAPHY':'VIKING · MDIM 2.1'}</small></div>
    <div className="globe-controls">
      <button onClick={()=>rotate(-Math.PI/6)} aria-label="Обернути Марс ліворуч"><ArrowLeft size={16}/></button>
      <button onClick={()=>rotate(Math.PI/6)} aria-label="Обернути Марс праворуч"><ArrowRight size={16}/></button>
      <button onClick={()=>zoom(.8)} aria-label="Наблизити планету">+</button>
      <button onClick={()=>zoom(1.25)} aria-label="Віддалити планету">−</button>
      <button onClick={showJezero}><Crosshair size={15} aria-hidden/>Показати Jezero</button>
      <button onClick={toggleFullscreen} aria-pressed={fullscreen}><ArrowsOut size={15} aria-hidden/>{fullscreen?'Вийти з глобуса':'Весь екран'}</button>
    </div>
    {!mission && <div className="globe-destination">
      <span className="eyebrow">ПІДГОТОВЛЕНИЙ РАЙОН ЕКСПЕДИЦІЇ</span><h3>Jezero Crater</h3>
      <p>18.4447° N / 77.4508° E<br/>{coverageBounds?'CTX DEM ≈ 30 × 30 км':'CTX DEM'} · локальний HiRISE · геологія</p>
      <button className="primary" onClick={onJezero}>Перейти до Jezero →</button>
      <small>Зелений маркер перебільшено для видимості; це не розмір кратера.</small>
    </div>}
    {!loaded && !error && <div className="terrain3d-message" role="status">Завантаження глобальної мозаїки Марса…</div>}
    {error && <div className="terrain3d-message" role="alert">{error}<button onClick={onFallback}>До 2D карти</button></div>}
    <div className="globe-note"><strong>{coordinates}</strong><br/>
      {route?.metrics?.snap_offsets_m.some(d=>d>.5)&&<>Світло-сіре — прив’язка до клітинок DEM, не перевірений проїзд.<br/></>}
      {detail?'NASA Trek: тайли підвантажуються за масштабом; CTX/HiRISE — чорно-білі знімки, не нові вимірювання висот.':'Реальна Viking-мозаїка, офіційно колоризована NASA Ames/USGS — не true-color фото.'}
      {terrain?` Рельєф MOLA · ${terrain.resolution_deg}° · підсилення висот ×${exaggeration}. Глобальні маршрути приблизні.`:' Сферичний огляд. Детальні маршрути — Jezero.'}
      {metadata && <a href={metadata.source_page} target="_blank" rel="noreferrer"> Першоджерело ↗</a>}
    </div>
  </div>
}
