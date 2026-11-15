// Runs the real atlas/shader in isolation, not a reimplementation of its maths.
import * as THREE from '../frontend/node_modules/three/build/three.module.js'
import { globeImagery } from '../frontend/src/components/globeImagery'

const renderer=new THREE.WebGLRenderer({antialias:false,preserveDrawingBuffer:true})
renderer.setSize(800,600);renderer.setPixelRatio(1)
document.body.style.margin='0';document.body.appendChild(renderer.domElement)
const camera=new THREE.PerspectiveCamera(38,800/600,.00001,50)
const scene=new THREE.Scene()
scene.add(new THREE.AmbientLight(0xffffff,Math.PI))
const base=document.createElement('canvas');base.width=4;base.height=2
const ctx=base.getContext('2d')!;ctx.fillStyle='#202020';ctx.fillRect(0,0,4,2)
const material=new THREE.MeshStandardMaterial({map:new THREE.CanvasTexture(base),roughness:1})
material.map!.colorSpace=THREE.SRGBColorSpace
scene.add(new THREE.Mesh(new THREE.SphereGeometry(1,360,180),material))
let status:any=null
const catalog={tiles:[{id:'ctx-global',title:'Unique coordinate test tiles',matrices:Array.from({length:18},(_,i)=>String(i)),max_useful_zoom:13}]}
const render=()=>{renderer.render(scene,camera)}
const atlas=globeImagery(material,camera,renderer,()=>({catalog:catalog as any,topography:false}),render,s=>{status=s})
function view(lon:number,lat:number,zoom:number){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  camera.position.set(1.16*Math.cos(b)*Math.cos(a),1.16*Math.sin(b),-1.16*Math.cos(b)*Math.sin(a))
  camera.lookAt(0,0,0);camera.zoom=zoom;camera.updateProjectionMatrix();render();atlas.schedule()
}
function samples(){
  const ray=new THREE.Raycaster(),sphere=new THREE.Sphere(new THREE.Vector3(),1)
  const output:any[]=[]
  camera.updateMatrixWorld()
  for(let y=90;y<550;y+=47)for(let x=70;x<750;x+=43){
    ray.setFromCamera(new THREE.Vector2(x/800*2-1,1-y/600*2),camera)
    const hit=ray.ray.intersectSphere(sphere,new THREE.Vector3())
    if(!hit)continue
    const lon=Math.atan2(-hit.z,hit.x)*180/Math.PI,lat=Math.asin(hit.y)*180/Math.PI
    const pixel=new Uint8Array(4)
    renderer.getContext().readPixels(x,599-y,1,1,renderer.getContext().RGBA,renderer.getContext().UNSIGNED_BYTE,pixel)
    output.push({x,y,lon,lat,rgb:Array.from(pixel.slice(0,3))})
  }
  return output
}
;(window as any).atlasFixture={view,samples,status:()=>status,dispose:()=>{atlas.dispose();renderer.dispose()}}
