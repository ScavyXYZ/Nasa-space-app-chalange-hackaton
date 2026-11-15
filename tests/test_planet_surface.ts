import assert from 'node:assert/strict'
import * as THREE from '../frontend/node_modules/three/build/three.module.js'
import { surfaceGeometry } from '../frontend/src/components/adaptiveGlobe'
import type { PlanetSurface } from '../frontend/src/components/adaptiveGlobe'
import { globeSurface } from '../frontend/src/components/globeSurface'
import { globeOpticalSource } from '../frontend/src/components/imageryLod'
import type { ImagerySource } from '../frontend/src/components/imageryLod'

const local={id:'viking-local',matrices:Array.from({length:6},(_,i)=>String(i)),max_useful_zoom:5} as ImagerySource
const photos=[
  {id:'viking-hd'}, {id:'ctx-global'},
  {id:'ctx-jezero',bounds:[77.16,18.21,77.70,18.73]},
  {id:'hirise-jezero',bounds:[77.22,18.30,77.59,18.67]},
] as ImagerySource[]
assert.equal(globeOpticalSource(photos,5,137.4,-4.6,local)?.id,'viking-local')
assert.equal(globeOpticalSource(photos,6,137.4,-4.6,local)?.id,'ctx-global')
assert.equal(globeOpticalSource(photos,9,77.45,18.44,local)?.id,'ctx-jezero')
assert.equal(globeOpticalSource(photos,13,77.45,18.44,local)?.id,'hirise-jezero')
assert.equal(globeOpticalSource(photos,13,137.4,-4.6,local)?.id,'ctx-global')
assert.equal(globeOpticalSource(photos,13,137.4,-4.6,local,false)?.id,'viking-local')
assert.equal(globeOpticalSource([],13,137.4,-4.6,local)?.id,'viking-local')

const geometry=new THREE.SphereGeometry(1,36,18)
const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial())
const drape=globeSurface(mesh) // Must follow subsequent geometry replacement.
const x=[-180,-120,-80,-40,-2,-1,-.5,0,.5,1,2,40,80,120,180]
const y=[90,60,30,2,1,.5,0,-.5,-1,-2,-30,-60,-90]
const heights=y.flatMap(lat=>x.map(lon=>1500*Math.cos(lat*Math.PI/180)*Math.cos(lon*Math.PI/180)))
const data={shape:[y.length,x.length],longitudes:x,latitudes:y,elevations_m:heights,
  radius_m:3396000} as PlanetSurface
mesh.geometry=surfaceGeometry(data,10)
mesh.updateMatrixWorld()
const positions=mesh.geometry.getAttribute('position'),normals=mesh.geometry.getAttribute('normal')
for(let row=0;row<y.length;row++){
  const a=row*x.length,b=a+x.length-1
  assert.deepEqual([positions.getX(a),positions.getY(a),positions.getZ(a)],
    [positions.getX(b),positions.getY(b),positions.getZ(b)])
  assert.deepEqual([normals.getX(a),normals.getY(a),normals.getZ(a)],
    [normals.getX(b),normals.getY(b),normals.getZ(b)])
}
const ray=new THREE.Raycaster()
let maxError=0
for(const [lon,lat] of [[0,0],[.23,-.71],[-.77,.32],[179,12],[-179,12],[45,85],
  ...Array.from({length:100},(_,i)=>[(i*137.507)%359-179,(i*61.314)%178-89])]){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  const direction=new THREE.Vector3(Math.cos(b)*Math.cos(a),Math.sin(b),-Math.cos(b)*Math.sin(a))
  ray.set(direction.clone().multiplyScalar(4),direction.clone().negate())
  const hit=ray.intersectObject(mesh,false)[0]
  assert.ok(hit,`Independent ray missed ${lon},${lat}`)
  const error=drape.point(lon,lat).distanceTo(hit.point)
  assert.ok(error<1e-9,`Wrong adaptive triangle ${lon},${lat}: ${error}`)
  maxError=Math.max(maxError,error)
}
console.log(JSON.stringify({status:'passed',geometry_swap_retains_drape:true,
  automatic_viking_ctx_hirise_selection:true,seam_positions_and_normals_identical:true,max_projection_error:maxError},null,2))
