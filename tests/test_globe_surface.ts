import assert from 'node:assert/strict'
import * as THREE from '../frontend/node_modules/three/build/three.module.js'
import { globeSurface } from '../frontend/src/components/globeSurface'
import { routeAnchors,splitLongitudeLine } from '../frontend/src/components/routeAnchors'
import type { GlobalRoute } from '../frontend/src/types'

const geometry=new THREE.SphereGeometry(1,360,180)
const vertices=geometry.getAttribute('position')
for(let i=0;i<vertices.count;i++){
  const v=new THREE.Vector3().fromBufferAttribute(vertices,i).normalize()
  v.multiplyScalar(1+.025*Math.sin(17*v.x)*Math.cos(13*v.y)*Math.sin(11*v.z))
  vertices.setXYZ(i,v.x,v.y,v.z)
}
geometry.computeBoundingSphere()
const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial())
mesh.updateMatrixWorld()
const surface=globeSurface(mesh),ray=new THREE.Raycaster()
function independent(lon:number,lat:number){
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  const normal=new THREE.Vector3(Math.cos(b)*Math.cos(a),Math.sin(b),-Math.cos(b)*Math.sin(a))
  ray.set(normal.clone().multiplyScalar(4),normal.clone().negate())
  let hit=ray.intersectObject(mesh,false)[0]
  // Exact Float32 seam vertices can leave a sub-nanometre raycasting crack.
  // An independent neighbouring ray checks its limiting surface position.
  if(!hit){
    const nearby=normal.clone().add(new THREE.Vector3(1e-12,1e-12,1e-12)).normalize()
    ray.set(nearby.clone().multiplyScalar(4),nearby.clone().negate())
    hit=ray.intersectObject(mesh,false)[0]
  }
  assert.ok(hit,`Independent ray missed ${lon},${lat}`)
  return hit.point
}
let maxError=0
const cases=[[180,0],[-180,0],[0,90],[0,-90],[179.999999,89.99999],[-179.999999,-89.99999],
  ...Array.from({length:180},(_,i)=>[-180+i*2,90-i]),
  ...Array.from({length:250},(_,i)=>[(i*137.507764)%360-180,(i*61.31419)%180-90])]
for(const [lon,lat] of cases){
  const error=surface.point(lon,lat).distanceTo(independent(lon,lat))
  maxError=Math.max(maxError,error)
  assert.ok(error<1e-9,`${lon},${lat}: ${error}`)
}
const began=performance.now()
let count=0,maxChordError=0
for(const coordinates of [[[179.8,20],[-179.8,20.2]],[[0,89.8],[180,89.8]],
  [[-97.15,24.02],[-98.12,23.71]],[[0,0],[70,35]]]){
  const line=surface.path(coordinates)
  count+=line.length
  for(let i=1;i<line.length;i++){
    const midpoint=line[i-1].clone().add(line[i]).multiplyScalar(.5)
    const unit=midpoint.clone().normalize()
    const expected=independent(Math.atan2(-unit.z,unit.x)*180/Math.PI,Math.asin(unit.y)*180/Math.PI)
    const error=midpoint.distanceTo(expected)
    maxChordError=Math.max(maxChordError,error)
    assert.ok(error<3e-7,`Drape sinks below terrain: ${error} at ${i}/${line.length} in ${JSON.stringify(coordinates)}`)
  }
}
const route={status:'ok',expanded_cells:0,route:{type:'Feature',properties:{},geometry:{
  type:'LineString',coordinates:[[0,0],[1,0],[2,0],[3,0],[4,0]]}},
  legs:[{distance_m:20},{distance_m:20}],
  profile:[0,10,20,30,40].map(distance_m=>({distance_m,elevation_m:0,interpolated:false}))} as GlobalRoute
const anchors=routeAnchors(route,[{lon:.01,lat:0},{lon:2.01,lat:0},{lon:4.01,lat:0}])
assert.deepEqual(anchors.map(a=>a.snapped.lon),[0,2,4])
assert.ok(anchors.every(a=>a.offsetM>590&&a.offsetM<595))
assert.deepEqual(splitLongitudeLine([[179,10],[-179,12]]),[[[179,10],[180,11]],[[-180,11],[-179,12]]])
assert.deepEqual(splitLongitudeLine([[-179,12],[179,10]]),[[[-179,12],[-180,11]],[[180,11],[179,10]]])
assert.deepEqual(splitLongitudeLine([[180,10],[-180,12]]),[[[180,10],[180,12]],[[-180,12]]])
assert.equal(routeAnchors({...route,profile:undefined,legs:undefined},
  [{lon:0,lat:0},{lon:2,lat:0},{lon:4,lat:0}]).length,2)
console.log(JSON.stringify({status:'passed',mesh_points:cases.length,max_projection_error:maxError,
  draped_vertices:count,max_chord_error:maxChordError,elapsed_ms:Math.round(performance.now()-began)},null,2))
