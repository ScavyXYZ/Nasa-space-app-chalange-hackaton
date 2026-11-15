import * as THREE from 'three'
import { api } from '../api'
import { longitudeNear } from './imageryLod'
import { planetView } from './planetView'

export type PlanetSurface={
  shape:[number,number];longitudes:number[];latitudes:number[];elevations_m:number[]
  level:number;focus:[number,number];detail_half_span_deg:number
  source:string;source_spacing_m:number;radius_m:number;display_step_deg:number
  interpolated_fraction:number;native_coverage_latitude:[number,number];polar_fallback:string
}
export type SurfaceStatus={level:number;vertices:number;spacing:number;loading:boolean;offline:boolean}

export function surfaceNormals(geometry:THREE.SphereGeometry){
  geometry.computeVertexNormals()
  const normals=geometry.getAttribute('normal')
  const width=geometry.parameters.widthSegments,height=geometry.parameters.heightSegments
  const normal=new THREE.Vector3()
  // Weld lighting across the duplicated equirectangular seam/poles too.
  for(let row=0;row<=height;row++){
    const a=row*(width+1),b=a+width
    normal.fromBufferAttribute(normals,a).add(new THREE.Vector3().fromBufferAttribute(normals,b)).normalize()
    normals.setXYZ(a,normal.x,normal.y,normal.z);normals.setXYZ(b,normal.x,normal.y,normal.z)
  }
  for(let col=0;col<=width;col++){
    normals.setXYZ(col,0,1,0);normals.setXYZ(height*(width+1)+col,0,-1,0)
  }
  normals.needsUpdate=true
}

/** Build ONE closed indexed sphere, including the low-detail far hemisphere.
 * All adjacent cells share vertices; there are no independent terrain patches.
 */
export function surfaceGeometry(data:PlanetSurface,exaggeration:number){
  const [rows,cols]=data.shape
  const geometry=new THREE.SphereGeometry(1,cols-1,rows-1)
  geometry.userData.surface=data
  const positions=geometry.getAttribute('position'),uv=geometry.getAttribute('uv')
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
    const i=r*cols+c,lon=data.longitudes[c]*Math.PI/180,lat=data.latitudes[r]*Math.PI/180
    const radius=1+data.elevations_m[i]*exaggeration/data.radius_m
    // Exactly identical pole and antimeridian vertices: no Float32 seam crack.
    const cos=Math.abs(data.latitudes[r])===90?0:Math.cos(lat)
    const sinLon=Math.abs(data.longitudes[c])===180?0:Math.sin(lon)
    positions.setXYZ(i,radius*cos*Math.cos(lon),radius*Math.sin(lat),-radius*cos*sinLon)
    uv.setXY(i,(data.longitudes[c]+180)/360,(data.latitudes[r]+90)/180)
  }
  positions.needsUpdate=true;uv.needsUpdate=true
  surfaceNormals(geometry);geometry.computeBoundingSphere()
  return geometry
}

export function adaptiveGlobe(mesh:THREE.Mesh<THREE.SphereGeometry>,camera:THREE.PerspectiveCamera,
  host:HTMLElement,getExaggeration:()=>number,changed:()=>void,status:(state:SurfaceStatus)=>void){
  let disposed=false,timer=0,sequence=0,key='',controller:AbortController|null=null
  let retryTimer=0,retries=0,retryKey=''
  let current:PlanetSurface|null=null
  const cache=new Map<string,PlanetSurface>()
  function report(loading=false,offline=false){
    host.dataset.surfaceLevel=String(current?.level??-1)
    host.dataset.surfaceVertices=String(mesh.geometry.getAttribute('position').count)
    host.dataset.surfaceSource=current?'mola128':'overview'
    host.dataset.surfaceLoading=String(loading)
    host.dataset.surfaceOffline=String(offline)
    status({level:current?.level??-1,vertices:mesh.geometry.getAttribute('position').count,
      spacing:current?.source_spacing_m??0,loading,offline})
  }
  function publish(data:PlanetSurface){
    const previous=mesh.geometry
    mesh.geometry=surfaceGeometry(data,getExaggeration())
    current=data
    // Route/pins/geology attach to the same new triangles before the next draw.
    changed();previous.dispose();report()
  }
  async function update(){
    if(disposed)return
    const view=planetView(camera)
    if(!view)return
    const span=Math.max(view.east-view.west,view.north-view.south)
    const level=Math.max(0,Math.min(8,Math.floor(Math.log2(64/Math.max(.000001,span)))))
    if(current&&current.level===level){
      const dx=Math.abs(longitudeNear(view.lon,current.focus[0])-current.focus[0])
      const dy=Math.abs(view.lat-current.focus[1])
      // A generous stable inner band prevents a request for every drag pixel.
      if(dx+span/2<current.detail_half_span_deg*.85&&dy+span/2<current.detail_half_span_deg*.85)return
      if(level===0)return // Uniform background is already global.
    }
    const quantum=(64/2**level)/4
    const lon=Math.max(-180,Math.min(180,Math.round(view.lon/quantum)*quantum))
    const lat=Math.max(-90,Math.min(90,Math.round(view.lat/quantum)*quantum))
    const next=`${level}:${lon}:${lat}`
    if(next===key)return
    if(next!==retryKey){retryKey=next;retries=0;clearTimeout(retryTimer)}
    key=next
    const id=++sequence
    controller?.abort();controller=new AbortController()
    const cached=cache.get(next)
    if(cached){cache.delete(next);cache.set(next,cached);publish(cached);return}
    report(true)
    try{
      const data=await api<PlanetSurface>(`/api/global/surface?lon=${lon}&lat=${lat}&level=${level}`,{signal:controller.signal})
      if(disposed||id!==sequence)return
      if(data.shape[0]*data.shape[1]>220000||data.elevations_m.length!==data.shape[0]*data.shape[1]
        ||data.elevations_m.some(h=>!Number.isFinite(h)||h< -9000||h>22000))throw Error('Invalid surface')
      cache.set(next,data)
      while(cache.size>4)cache.delete(cache.keys().next().value!)
      clearTimeout(retryTimer);retries=0
      publish(data)
    }catch(error){
      if(!disposed&&id===sequence&&(error as Error).name!=='AbortError'){
        // Keep the complete previous globe and permit an explicit later retry.
        key='';report(false,true)
        // Cold-start contention or a brief connection loss is recoverable.
        // Bounded retries only; never replace the retained mesh with a blank.
        if(retries<2){
          retries++
          retryTimer=window.setTimeout(()=>{retryTimer=0;void update()},500*retries)
        }
      }
    }
  }
  return {
    schedule:()=>{
      if(disposed||timer)return
      timer=window.setTimeout(()=>{timer=0;void update()},120)
    },
    data:()=>current,
    dispose:()=>{disposed=true;sequence++;clearTimeout(timer);clearTimeout(retryTimer);controller?.abort();cache.clear()},
  }
}
