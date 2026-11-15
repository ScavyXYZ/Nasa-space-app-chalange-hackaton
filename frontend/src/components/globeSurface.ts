import * as THREE from 'three'

const direction=(lon:number,lat:number)=>{
  const a=lon*Math.PI/180,b=lat*Math.PI/180
  return new THREE.Vector3(Math.cos(b)*Math.cos(a),Math.sin(b),-Math.cos(b)*Math.sin(a))
}

/** Project onto the actual rendered triangles, not a separately sampled radius. */
export function globeSurface(mesh:THREE.Mesh<THREE.SphereGeometry>){
  const ray=new THREE.Ray(),caster=new THREE.Raycaster()
  const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3(),d=new THREE.Vector3()
  function point(lon:number,lat:number){
    const geometry=mesh.geometry,width=geometry.parameters.widthSegments,height=geometry.parameters.heightSegments
    const normal=direction(lon,lat),target=new THREE.Vector3()
    ray.set(new THREE.Vector3(),normal)
    const axes=geometry.userData.surface as {longitudes:number[];latitudes:number[]}|undefined
    function interval(values:number[],value:number,descending=false){
      let lo=0,hi=values.length-1
      while(hi-lo>1){
        const mid=(lo+hi)>>1
        if(descending?values[mid]>=value:values[mid]<=value)lo=mid;else hi=mid
      }
      return Math.min(values.length-2,lo)
    }
    const x=axes?interval(axes.longitudes,((lon+180)%360+360)%360-180)
      :Math.min(width-1,Math.floor((((lon+180)%360+360)%360)/360*width))
    const y=axes?interval(axes.latitudes,lat,true)
      :Math.max(0,Math.min(height-1,Math.floor((90-lat)/180*height)))
    const positions=geometry.getAttribute('position')
    function cell(row:number,col:number){
      if(row<0||row>=height)return false
      col=(col+width)%width
      const top=row*(width+1)+col,bottom=(row+1)*(width+1)+col
      a.fromBufferAttribute(positions,top+1);b.fromBufferAttribute(positions,top)
      c.fromBufferAttribute(positions,bottom);d.fromBufferAttribute(positions,bottom+1)
      return (row!==0&&ray.intersectTriangle(a,b,d,false,target)!==null)
        ||(row!==height-1&&ray.intersectTriangle(b,c,d,false,target)!==null)
    }
    if(cell(y,x))return target
    for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){
      if((dr||dc)&&cell(y+dr,x+dc))return target
    }
    // Pole/roundoff fallback remains a real mesh intersection.
    caster.set(normal.clone().multiplyScalar(4),normal.clone().negate())
    const hit=caster.intersectObject(mesh,false)[0]
    if(hit)return hit.point.clone()
    // Float32 seam vertices can leave a tiny crack exactly at ±180°.
    // Use a neighbouring real triangle's radius, not an invented sphere.
    const nearby=normal.clone().add(new THREE.Vector3(1e-12,1e-12,1e-12)).normalize()
    caster.set(nearby.clone().multiplyScalar(4),nearby.clone().negate())
    const neighbour=caster.intersectObject(mesh,false)[0]
    if(neighbour)return normal.multiplyScalar(neighbour.point.length())
    throw new Error('Rendered Mars surface intersection unavailable')
  }
  function arc(from:THREE.Vector3,to:THREE.Vector3,output:THREE.Vector3[],depth=0){
    const midDirection=from.clone().normalize().add(to.clone().normalize()).normalize()
    const lat=Math.asin(THREE.MathUtils.clamp(midDirection.y,-1,1))*180/Math.PI
    const lon=Math.atan2(-midDirection.z,midDirection.x)*180/Math.PI
    const mid=point(lon,lat),chord=from.clone().add(to).multiplyScalar(.5)
    if(depth<18&&mid.distanceTo(chord)>1e-7){
      arc(from,mid,output,depth+1);arc(mid,to,output,depth+1)
    }else output.push(to)
  }
  function path(coordinates:number[][]){
    if(!coordinates.length)return []
    const output=[point(coordinates[0][0],coordinates[0][1])]
    coordinates.slice(1).forEach(p=>arc(output[output.length-1],point(p[0],p[1]),output))
    return output
  }
  return {point,path}
}

/** Depth-only bias: no kilometre-scale radial lift or screen-space parallax. */
export function surfaceLineMaterial<T extends THREE.LineBasicMaterial>(material:T):T{
  material.depthWrite=false
  material.onBeforeCompile=shader=>{
    shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',`#include <project_vertex>
      gl_Position.z += projectionMatrix[3][2] * 0.000003 / max(gl_Position.w, 0.0001);`)
  }
  material.customProgramCacheKey=()=>'surface-depth-bias-v1'
  return material
}
