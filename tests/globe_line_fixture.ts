import * as THREE from '../frontend/node_modules/three/build/three.module.js'
import { globeSurface,surfaceLineMaterial } from '../frontend/src/components/globeSurface'

const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true})
renderer.setSize(800,600);renderer.setPixelRatio(1)
document.body.style.margin='0';document.body.appendChild(renderer.domElement)
const scene=new THREE.Scene();scene.background=new THREE.Color('#080c12')
const camera=new THREE.PerspectiveCamera(38,800/600,.01,50)
const geometry=new THREE.SphereGeometry(1,360,180)
const vertices=geometry.getAttribute('position')
for(let i=0;i<vertices.count;i++){
  const v=new THREE.Vector3().fromBufferAttribute(vertices,i).normalize()
  v.multiplyScalar(1+.015*Math.sin(17*v.x)*Math.cos(13*v.y)*Math.sin(11*v.z))
  vertices.setXYZ(i,v.x,v.y,v.z)
}
geometry.computeBoundingSphere()
const globe=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:'#303840'}));scene.add(globe)
globe.updateMatrixWorld()
const surface=globeSurface(globe)
const line=new THREE.Line(new THREE.BufferGeometry(),surfaceLineMaterial(new THREE.LineBasicMaterial({color:'#f0b180'})))
scene.add(line)
const back=new THREE.Line(new THREE.BufferGeometry(),surfaceLineMaterial(new THREE.LineBasicMaterial({color:'#00ff00'})))
scene.add(back)
function view(lon:number,lat:number,zoom:number){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  camera.position.set(1.16*Math.cos(b)*Math.cos(a),1.16*Math.sin(b),-1.16*Math.cos(b)*Math.sin(a))
  camera.lookAt(0,0,0);camera.zoom=zoom;camera.updateProjectionMatrix();camera.updateMatrixWorld()
  const coordinates=Array.from({length:21},(_,i)=>[lon+(-1.8+i*.18)/zoom,lat+(.2+.15*Math.sin(i*.4))/zoom])
  const points=surface.path(coordinates)
  line.geometry.dispose();line.geometry=new THREE.BufferGeometry().setFromPoints(points)
  back.geometry.dispose()
  back.geometry=new THREE.BufferGeometry().setFromPoints(points.map(p=>p.clone().negate()))
  renderer.render(scene,camera)
  const projected=points.map(p=>p.clone().project(camera)).map(p=>({x:(p.x+1)*400,y:(1-p.y)*300}))
  const context=renderer.getContext()
  const pixels=new Uint8Array(800*600*4)
  context.readPixels(0,0,800,600,context.RGBA,context.UNSIGNED_BYTE,pixels)
  let visible=0,tested=0,backPixels=0
  for(let i=1;i<projected.length;i++){
    const a=projected[i-1],b=projected[i],steps=Math.max(1,Math.ceil(Math.hypot(a.x-b.x,a.y-b.y)/2))
    for(let j=0;j<=steps;j++){
      const x=Math.round(a.x+(b.x-a.x)*j/steps),y=Math.round(a.y+(b.y-a.y)*j/steps)
      if(x<3||x>796||y<3||y>596)continue
      tested++
      let found=false
      for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){
        const k=((599-y-dy)*800+x+dx)*4
        if(pixels[k]>125&&pixels[k]>pixels[k+1]*1.15&&pixels[k+1]>pixels[k+2]*1.1)found=true
      }
      if(found)visible++
    }
  }
  for(let k=0;k<pixels.length;k+=4)if(pixels[k+1]>150&&pixels[k]<50&&pixels[k+2]<50)backPixels++
  return {zoom,vertices:points.length,tested,visible,coverage:visible/tested,backPixels}
}
;(window as any).lineFixture={view}
