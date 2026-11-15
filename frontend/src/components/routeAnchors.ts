import type { GlobalRoute,Position } from '../types'

export function splitLongitudeLine(coordinates:number[][]){
  if(!coordinates.length)return []
  const lines:number[][][]=[[coordinates[0]]]
  coordinates.slice(1).forEach((b,i)=>{
    const a=coordinates[i]
    if(Math.abs(b[0]-a[0])>180){
      const longitude=b[0]+(b[0]<a[0]?360:-360)
      if(Math.abs(longitude-a[0])<1e-12){
        lines[lines.length-1].push([a[0],b[1]])
        lines.push([b])
        return
      }
      const edge=longitude>a[0]?180:-180
      const lat=a[1]+(b[1]-a[1])*(edge-a[0])/(longitude-a[0])
      lines[lines.length-1].push([edge,lat])
      lines.push([[-edge,lat]])
    }
    lines[lines.length-1].push(b)
  })
  return lines
}

export function routeAnchors(route:GlobalRoute|null|undefined,selected:(Position|null)[]){
  const g=route?.route?.geometry
  const coordinates=g?.type==='LineString'?g.coordinates:g?.type==='Point'?[g.coordinates]:[]
  if(!coordinates.length)return []
  const actual=selected.filter((p):p is Position=>p!==null)
  if(actual.length<2)return []
  let travelled=0
  return actual.flatMap((p,i)=>{
    if(i)travelled+=route?.legs?.[i-1]?.distance_m??0
    const index=i===0?0:i===actual.length-1?coordinates.length-1:
      route?.profile?.findIndex(sample=>sample.distance_m>=travelled-1e-5)??-1
    // Without leg/profile correspondence, don't invent a stop-to-grid link.
    if(index<0||i>0&&i<actual.length-1&&!route?.legs?.[i-1])return []
    const cell=coordinates[Math.min(index,coordinates.length-1)]
    const snapped={lon:cell[0],lat:cell[1]}
    const rad=Math.PI/180
    const h=Math.sin((p.lat-snapped.lat)*rad/2)**2
      +Math.cos(p.lat*rad)*Math.cos(snapped.lat*rad)*Math.sin((p.lon-snapped.lon)*rad/2)**2
    return [{actual:p,snapped,offsetM:2*3396000*Math.asin(Math.sqrt(Math.min(1,h)))}]
  })
}
