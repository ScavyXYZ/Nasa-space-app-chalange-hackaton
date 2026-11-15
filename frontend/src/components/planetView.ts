import * as THREE from 'three'
import { longitudeNear } from './imageryLod'

/** Geographic footprint of the current view. No camera mutation. */
export function planetView(camera:THREE.PerspectiveCamera){
  // Oblique views of exaggerated mountains must use the visible surface
  // radius, not the datum sphere kilometres underneath the camera's target.
  const radius=Number(camera.userData.surfaceRadius)||1
  const ray=new THREE.Raycaster(),sphere=new THREE.Sphere(new THREE.Vector3(),radius)
  camera.updateMatrixWorld()
  ray.setFromCamera(new THREE.Vector2(0,0),camera)
  const centre=ray.ray.intersectSphere(sphere,new THREE.Vector3())
  if(!centre)return null
  centre.normalize()
  const lon=Math.atan2(-centre.z,centre.x)*180/Math.PI,lat=Math.asin(centre.y)*180/Math.PI
  const points:{lon:number;lat:number}[]=[]
  for(let y=-1;y<=1.01;y+=.25)for(let x=-1;x<=1.01;x+=.25){
    ray.setFromCamera(new THREE.Vector2(x,y),camera)
    const hit=ray.ray.intersectSphere(sphere,new THREE.Vector3())
    if(hit){hit.normalize();points.push({lon:longitudeNear(Math.atan2(-hit.z,hit.x)*180/Math.PI,lon),
      lat:Math.asin(THREE.MathUtils.clamp(hit.y,-1,1))*180/Math.PI})
    }
  }
  if(!points.length)return null
  const west=Math.min(...points.map(p=>p.lon)),east=Math.max(...points.map(p=>p.lon))
  const south=Math.min(...points.map(p=>p.lat)),north=Math.max(...points.map(p=>p.lat))
  const mx=Math.max(.000001,(east-west)*.03),my=Math.max(.000001,(north-south)*.03)
  return {lon,lat,west:west-mx,east:east+mx,south:Math.max(-90,south-my),north:Math.min(90,north+my)}
}
