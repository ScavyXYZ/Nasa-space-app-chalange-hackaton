import type { CraterHazard } from '../types'

/** Published circle fit + explicit policy buffer, not a measured rim polygon. */
export function craterRing(crater:CraterHazard){
  const lat=crater.lat*Math.PI/180,lon=crater.lon*Math.PI/180,r=crater.exclusion_radius_m/3396000
  return Array.from({length:73},(_,i)=>{
    const bearing=i/72*2*Math.PI
    const phi=Math.asin(Math.sin(lat)*Math.cos(r)+Math.cos(lat)*Math.sin(r)*Math.cos(bearing))
    const lambda=lon+Math.atan2(Math.sin(bearing)*Math.sin(r)*Math.cos(lat),Math.cos(r)-Math.sin(lat)*Math.sin(phi))
    return {lon:((lambda*180/Math.PI+540)%360)-180,lat:phi*180/Math.PI}
  })
}
