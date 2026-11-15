import * as THREE from 'three'
import { assetUrl } from '../api'
import { detailGrid, longitudeNear, opticalSource, tileSpacing } from './imageryLod'
import type { AtlasCatalog } from '../types'

type DetailState={catalog:AtlasCatalog|null|undefined;topography:boolean}
export type DetailStatus={source:string;zoom:number;ready:number;total:number;fallback:number;preview:boolean;spacing:number;limited:boolean;offline:boolean}

/** One bounded regional texture atlas, projected into the base sphere's UVs.
 * Geometry, elevation values and route calculations are intentionally unchanged.
 */
export function globeImagery(material:THREE.MeshStandardMaterial,camera:THREE.PerspectiveCamera,
  renderer:THREE.WebGLRenderer,getState:()=>DetailState,render:()=>void,
  status:(s:DetailStatus|null)=>void){
  const uniforms={
    detailMap:{value:null as THREE.Texture|null},detailBounds:{value:new THREE.Vector4()},
    detailEnabled:{value:0},
  }
  material.onBeforeCompile=shader=>{
    Object.assign(shader.uniforms,uniforms)
    shader.fragmentShader=`uniform sampler2D detailMap;\nuniform vec4 detailBounds;\nuniform float detailEnabled;\n`+shader.fragmentShader
    shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>',`#include <map_fragment>
      #ifdef USE_MAP
      if (detailEnabled > 0.5) {
        float dx = mod(vMapUv.x - detailBounds.x + 1.0, 1.0);
        vec2 detailUv = vec2(dx / detailBounds.z, (vMapUv.y - detailBounds.y) / detailBounds.w);
        if (detailUv.x >= 0.0 && detailUv.x <= 1.0 && detailUv.y >= 0.0 && detailUv.y <= 1.0) {
          vec4 detail = texture2D(detailMap, detailUv);
          vec2 edge = min(detailUv, 1.0 - detailUv);
          float fade = smoothstep(0.0, 0.008, min(edge.x, edge.y));
          diffuseColor.rgb = mix(diffuseColor.rgb, detail.rgb, detail.a * fade);
        }
      }
      #endif`)
  }
  material.customProgramCacheKey=()=>'mars-original-tile-atlas-v3'
  material.needsUpdate=true
  let disposed=false,generation=0,key='',frame=0,current:THREE.CanvasTexture|null=null
  let timer=0
  type Grid=NonNullable<ReturnType<typeof detailGrid>>
  let active:{grid:Grid;source:string;zoom:number;topography:boolean}|null=null
  // A camera move cancels composition, not useful downloads shared by views.
  const abort=new AbortController()
  const images=new Map<string,ImageBitmap>()
  const pending=new Map<string,Promise<ImageBitmap>>()
  const controllers=new Map<string,AbortController>()
  async function loadImage(cacheKey:string,id:number):Promise<ImageBitmap>{
    if(disposed||id!==generation)throw Error('Obsolete view')
    const cached=images.get(cacheKey)
    if(cached){images.delete(cacheKey);images.set(cacheKey,cached);return cached}
    const existing=pending.get(cacheKey)
    if(existing)return existing
    if(pending.size>=6){
      await Promise.race([...pending.values()].map(request=>request.catch(()=>null)))
      return loadImage(cacheKey,id)
    }
    const controller=new AbortController()
    const timeout=window.setTimeout(()=>controller.abort(),15000)
    controllers.set(cacheKey,controller)
    const request=(async()=>{
      const response=await fetch(assetUrl('/api/atlas/tiles/'+cacheKey+'?v=validated-3'),{signal:controller.signal})
      if(!response.ok)throw Error('Tile unavailable')
      const image=await createImageBitmap(await response.blob())
      if(disposed){image.close();throw Error('Viewer disposed')}
      images.set(cacheKey,image)
      while(images.size>192){const oldest=images.keys().next().value!;images.get(oldest)?.close();images.delete(oldest)}
      return image
    })()
    pending.set(cacheKey,request)
    try{return await request}finally{clearTimeout(timeout);pending.delete(cacheKey);controllers.delete(cacheKey)}
  }
  const ray=new THREE.Raycaster(),sphere=new THREE.Sphere(new THREE.Vector3(),1)
  function visibleRegion(){
    camera.updateMatrixWorld()
    ray.setFromCamera(new THREE.Vector2(0,0),camera)
    const centre=ray.ray.intersectSphere(sphere,new THREE.Vector3())
    if(!centre)return null
    const lon=Math.atan2(-centre.z,centre.x)*180/Math.PI,lat=Math.asin(centre.y)*180/Math.PI
    const points:{lon:number;lat:number}[]=[]
    for(let y=-1;y<=1.01;y+=.25)for(let x=-1;x<=1.01;x+=.25){
      ray.setFromCamera(new THREE.Vector2(x,y),camera)
      const hit=ray.ray.intersectSphere(sphere,new THREE.Vector3())
      if(hit)points.push({lon:longitudeNear(Math.atan2(-hit.z,hit.x)*180/Math.PI,lon),lat:Math.asin(THREE.MathUtils.clamp(hit.y,-1,1))*180/Math.PI})
    }
    if(!points.length)return null
    const west=Math.min(...points.map(p=>p.lon)),east=Math.max(...points.map(p=>p.lon))
    const south=Math.min(...points.map(p=>p.lat)),north=Math.max(...points.map(p=>p.lat))
    const mx=Math.max(.000001,(east-west)*.03),my=Math.max(.000001,(north-south)*.03)
    return {lon,lat,west:west-mx,east:east+mx,south:Math.max(-90,south-my),north:Math.min(90,north+my)}
  }
  async function update(){
    if(disposed)return
    const state=getState(),region=visibleRegion()
    if(!state.catalog||!region){
      generation++;key='';uniforms.detailEnabled.value=0;status(null);render();return
    }
    const wanted=Math.max(0,Math.ceil(Math.log2(renderer.domElement.width*360/(Math.max(.000001,region.east-region.west)*512))))
    const source=state.topography
      ?state.catalog.tiles.find(s=>s.id==='hrsc')
      :opticalSource(state.catalog.tiles,wanted,region.lon,region.lat)
    if(!source)return
    const sourceMax=source.max_useful_zoom??source.matrices.length-1
    let zoom=Math.min(wanted,sourceMax)
    let grid=detailGrid(region.lon,region.south,region.north,region.west,region.east,zoom)
    while(!grid&&zoom>0){zoom--;grid=detailGrid(region.lon,region.south,region.north,region.west,region.east,zoom)}
    if(!grid)return
    // Keep a stable atlas while the viewport remains inside its prefetched rim.
    // Rebuilding on every tile-boundary crossing caused partial atlases to
    // repeatedly replace each other, discarding their only remaining fallback.
    if(active&&active.source===source.id&&active.zoom===zoom&&active.topography===state.topography){
      const west=longitudeNear(active.grid.west+active.grid.longitudeSpan/2,region.lon)-active.grid.longitudeSpan/2
      const inset=180/2**zoom*.25
      if(region.west>=west+inset&&region.east<=west+active.grid.longitudeSpan-inset
        &&region.south>=active.grid.south+inset&&region.north<=active.grid.south+active.grid.latitudeSpan-inset)return
    }
    const step=180/2**zoom
    grid=detailGrid(region.lon,Math.max(-90,region.south-step),Math.min(90,region.north+step),
      region.west-step,region.east+step,zoom)??grid
    const nextKey=[source.id,zoom,grid.west,grid.south,grid.width,grid.height].join(':')
    if(nextKey===key)return
    key=nextKey
    const signal=abort.signal,id=++generation
    const required=new Set(grid.tiles.map(tile=>`${source.id}/${zoom}/${tile.y}/${tile.x}`))
    const previewZoom=Math.max(0,zoom-3)
    const previewGrid=previewZoom<zoom
      ?detailGrid(region.lon,region.south,region.north,region.west,region.east,previewZoom):null
    previewGrid?.tiles.forEach(tile=>required.add(`${source.id}/${previewZoom}/${tile.y}/${tile.x}`))
    // Only obsolete offscreen downloads are cancelled. Overlap stays in flight.
    // Otherwise six slow requests from a distant view can block the new centre.
    controllers.forEach((controller,tile)=>{if(!required.has(tile))controller.abort()})
    const canvas=document.createElement('canvas');canvas.width=grid.width*256;canvas.height=grid.height*256
    const ctx=canvas.getContext('2d')!
    let inherited=false
    // Rebuild ONLY from original georeferenced images, never from a resampled
    // composite. Repeated pan/zoom must not propagate stale or distorted pixels.
    const sourceOrder=state.topography?['hrsc']:['viking-hd','ctx-global','ctx-jezero','hirise-jezero']
    const cached=[...images.entries()].map(([key,image])=>{
      const [source,z,y,x]=key.split('/')
      return {source,zoom:Number(z),y:Number(y),x:Number(x),image}
    }).filter(t=>sourceOrder.includes(t.source))
      .sort((a,b)=>a.zoom-b.zoom||sourceOrder.indexOf(a.source)-sourceOrder.indexOf(b.source))
    for(const tile of cached){
      const span=180/2**tile.zoom
      const west=longitudeNear(-180+(tile.x+.5)*span,grid.west+grid.longitudeSpan/2)-span/2
      for(const shift of [-360,0,360]){
        const x=(west+shift-grid.west)/grid.longitudeSpan*canvas.width
        const y=(grid.south+grid.latitudeSpan-(90-tile.y*span))/grid.latitudeSpan*canvas.height
        const width=span/grid.longitudeSpan*canvas.width
        const height=span/grid.latitudeSpan*canvas.height
        if(x<canvas.width&&x+width>0&&y<canvas.height&&y+height>0){
          ctx.drawImage(tile.image,x,y,width,height)
          inherited=true
        }
      }
    }
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace
    texture.anisotropy=Math.min(16,renderer.capabilities.getMaxAnisotropy())
    let completed=0,ready=0,fallback=0,published=false,preview=false
    const baseStatus={source:source.title,zoom,total:grid.tiles.length,spacing:tileSpacing(zoom,region.lat),limited:wanted>sourceMax}
    status({...baseStatus,ready:0,fallback:0,preview:false,offline:false})
    const publish=()=>{
      if(disposed||id!==generation)return
      if(!published&&(ready||inherited)){
        current?.dispose()
        current=texture;published=true
        active={grid,source:source.id,zoom,topography:state.topography}
        uniforms.detailMap.value=texture
        uniforms.detailBounds.value.set(((grid.west+180)/360%1+1)%1,(grid.south+90)/180,grid.longitudeSpan/360,grid.latitudeSpan/180)
        uniforms.detailEnabled.value=1
      }
      if(published)texture.needsUpdate=true
      status({...baseStatus,ready,fallback,preview,offline:completed===grid.tiles.length&&ready<completed})
      render()
    }
    const work=[...grid.tiles].sort((a,b)=>{
      const cx=(longitudeNear(region.lon,grid.west+grid.longitudeSpan/2)-grid.west)/grid.longitudeSpan*grid.width
      const cy=(grid.south+grid.latitudeSpan-region.lat)/grid.latitudeSpan*grid.height
      return Math.hypot(a.dx+.5-cx,a.dy+.5-cy)-Math.hypot(b.dx+.5-cx,b.dy+.5-cy)
    })
    // Cached visible tiles must not wait behind six slow uncached requests.
    const missing=work.filter(tile=>{
      const image=images.get(`${source.id}/${zoom}/${tile.y}/${tile.x}`)
      if(!image)return true
      ctx.drawImage(image,tile.dx*256,tile.dy*256,256,256);completed++;ready++
      return false
    })
    work.splice(0,work.length,...missing)
    // Publish inherited pixels immediately, even if no new request has finished.
    // `ready` still counts only native tiles, not resampled fallback imagery.
    if(inherited||ready)publish()
    const previews=[...(previewGrid?.tiles??[])]
    async function previewWorker(){
      while(previews.length&&id===generation&&!disposed){
        const tile=previews.shift()!
        try{
          const image=await loadImage(`${source!.id}/${previewZoom}/${tile.y}/${tile.x}`,id)
          if(id!==generation||disposed)return
          const span=180/2**previewZoom
          const west=longitudeNear(-180+(tile.x+.5)*span,grid!.west+grid!.longitudeSpan/2)-span/2
          const x=(west-grid!.west)/grid!.longitudeSpan*canvas.width
          const y=(grid!.south+grid!.latitudeSpan-(90-tile.y*span))/grid!.latitudeSpan*canvas.height
          ctx.globalCompositeOperation='destination-over'
          ctx.drawImage(image,x,y,span/grid!.longitudeSpan*canvas.width,span/grid!.latitudeSpan*canvas.height)
          ctx.globalCompositeOperation='source-over'
          inherited=true;preview=true;publish()
        }catch{/* The complete local Viking overview is always underneath. */}
      }
    }
    async function worker(){
      while(work.length&&!signal.aborted&&!disposed&&id===generation){
        const tile=work.shift()!,cacheKey=`${source!.id}/${zoom}/${tile.y}/${tile.x}`
        try{
          // Reuse downloads still in flight after small drags or zoom changes.
          // Old generations finish at most their current six tiles.
          let image:ImageBitmap|undefined
          for(let attempt=0;attempt<2;attempt++){
            try{image=await loadImage(cacheKey,id);break}
            catch(error){
              if(attempt||id!==generation||disposed)throw error
              await new Promise(resolve=>window.setTimeout(resolve,250))
            }
          }
          if(id!==generation)break
          if(!image)throw Error('Tile unavailable')
          ctx.drawImage(image,tile.dx*256,tile.dy*256,256,256);ready++
        }catch(e){
          if(signal.aborted||disposed||id!==generation)break
          // A genuinely broken upstream tile must not become a blank rectangle
          // or a stretched neighbouring tile. Crop its own coarser ancestor.
          for(let level=zoom-1;level>=Math.max(0,zoom-3);level--){
            const scale=2**(zoom-level)
            try{
              const image=await loadImage(`${source!.id}/${level}/${Math.floor(tile.y/scale)}/${Math.floor(tile.x/scale)}`,id)
              if(id!==generation||disposed)break
              const width=image.width/scale,height=image.height/scale
              ctx.drawImage(image,(tile.x%scale)*width,(tile.y%scale)*height,width,height,
                tile.dx*256,tile.dy*256,256,256)
              inherited=true;fallback++;break
            }catch{/* Try the next genuine ancestor, never a neighbouring tile. */}
          }
        }
        completed++
        if(completed===1||completed%4===0||completed===grid!.tiles.length)publish()
      }
    }
    // Two short coarse requests get reserved slots instead of waiting behind
    // six slow native requests. Publish preview first, refine progressively.
    await Promise.all([previewWorker(),previewWorker(),...Array.from({length:4},()=>worker())])
    if(id===generation&&!disposed&&!signal.aborted)publish()
    if(!published)texture.dispose()
    if(id===generation&&!disposed){
      const nextZoom=zoom+1
      const nextSource=state.topography?source:opticalSource(state.catalog!.tiles,nextZoom,region.lon,region.lat)
      if(nextSource&&nextZoom<nextSource.matrices.length&&nextZoom<=(nextSource.max_useful_zoom??Infinity)){
        const span=180/2**nextZoom
        const nextGrid=detailGrid(region.lon,Math.max(-90,region.lat-span),Math.min(90,region.lat+span),
          region.lon-span,region.lon+span,nextZoom)
        const ahead=[...(nextGrid?.tiles??[])].slice(0,12)
        async function prefetch(){
          while(ahead.length&&id===generation&&!disposed){
            const tile=ahead.shift()!
            try{await loadImage(`${nextSource!.id}/${nextZoom}/${tile.y}/${tile.x}`,id)}
            catch{/* Opportunistic only; never delay or replace visible imagery. */}
          }
        }
        void Promise.all([prefetch(),prefetch()])
      }
    }
  }
  return {
    schedule:()=>{
      if(disposed)return
      // Throttle rather than debounce: continuous dragging must not starve LOD.
      if(timer)return
      timer=window.setTimeout(()=>{timer=0;frame=requestAnimationFrame(()=>void update())},60)
    },
    dispose:()=>{
      disposed=true;generation++;cancelAnimationFrame(frame);clearTimeout(timer);abort?.abort()
      controllers.forEach(controller=>controller.abort());active=null
      current?.dispose();images.forEach(image=>image.close());images.clear()
      uniforms.detailEnabled.value=0
    },
  }
}
