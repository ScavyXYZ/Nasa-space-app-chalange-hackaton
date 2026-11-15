import type { AtlasCatalog } from '../types'
export type ImagerySource=AtlasCatalog['tiles'][number]
export const MARS_CIRCUMFERENCE=2*Math.PI*3396000
export function insideSource(source:ImagerySource,lon:number,lat:number){
  const b=source.bounds??[-180,-90,180,90]
  return lon>=b[0]&&lon<=b[2]&&lat>=b[1]&&lat<=b[3]
}
export function opticalSource(sources:ImagerySource[],zoom:number,lon:number,lat:number){
  const ids=zoom>=13?['hirise-jezero','ctx-jezero','ctx-global','viking-hd']
    :zoom>=9?['ctx-jezero','ctx-global','viking-hd']:zoom>=4?['ctx-global','viking-hd']:['viking-hd']
  return ids.map(id=>sources.find(s=>s.id===id)).find(s=>s&&insideSource(s,lon,lat))??null
}
export function tileSpacing(zoom:number,latitude=0){
  return MARS_CIRCUMFERENCE*Math.cos(latitude*Math.PI/180)/(512*2**zoom)
}
export function longitudeNear(lon:number,centre:number){
  return centre+((lon-centre+540)%360)-180
}
export function detailGrid(centreLon:number,south:number,north:number,west:number,east:number,zoom:number){
  const rows=2**zoom,cols=rows*2,step=180/rows
  // Unwrapped x coordinates preserve adjacency across +/-180 degrees.
  const x0=Math.floor((west+180)/step),x1=Math.floor((east+180)/step)
  const y0=Math.max(0,Math.floor((90-north)/step)),y1=Math.min(rows-1,Math.floor((90-south)/step))
  const width=x1-x0+1,height=y1-y0+1
  if(width<1||height<1||width>12||height>12||width*height>96)return null
  const tiles=[]
  for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++)tiles.push({x:((x%cols)+cols)%cols,y,dx:x-x0,dy:y-y0})
  return {tiles,width,height,west:x0*step-180,south:90-(y1+1)*step,
    longitudeSpan:width*step,latitudeSpan:height*step,centreLon}
}
