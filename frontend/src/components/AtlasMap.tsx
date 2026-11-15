import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { AtlasCatalog, GlobalRoute, Position } from '../types'
import { api, assetUrl } from '../api'
import { insideSource, opticalSource, tileSpacing } from './imageryLod'
import type { FeatureCollection } from 'geojson'
import { strategicRoute } from './routeAssessment'
import { craterRing } from './hazardGeometry'
import { routeAnchors,splitLongitudeLine } from './routeAnchors'

type Props={catalog:AtlasCatalog|null;layer:string;geology:boolean;start:Position|null;end:Position|null;stops:Position[];route:GlobalRoute|null;focus:Position|null;onPick:(p:Position)=>void;onLocal:()=>void}
export default function AtlasMap(props:Props){
  const host=useRef<HTMLDivElement>(null),map=useRef<L.Map|null>(null),callback=useRef(props.onPick)
  callback.current=props.onPick
  const [zoom,setZoom]=useState(1)
  const [centre,setCentre]=useState({lon:-100,lat:15})
  const [context,setContext]=useState<[[number,number],[number,number]]|null>(null)
  const [geologicalFeatures,setGeologicalFeatures]=useState<FeatureCollection|null>(null)
  const layers=useRef<L.LayerGroup|null>(null),drawing=useRef<L.LayerGroup|null>(null)
  const geologyLayers=useRef<L.LayerGroup|null>(null)
  const terrainLayers=useRef<L.LayerGroup|null>(null)
  const [extent,setExtent]=useState<[number,number,number,number]|null>(null)
  const chosen=props.layer==='auto'?opticalSource(props.catalog?.tiles??[],zoom,centre.lon,centre.lat):props.catalog?.tiles.find(t=>t.id===props.layer)
  const sourceId=chosen?.id
  const previewSource=props.catalog?.tiles.find(t=>t.id==='ctx-global')
  const previewEnabled=zoom>6&&sourceId!=='viking-hd'&&sourceId!==undefined&&!!previewSource
  const local=!!context&&centre.lon>=context[0][1]&&centre.lon<=context[1][1]&&centre.lat>=context[0][0]&&centre.lat<=context[1][0]
  useEffect(()=>{
    const abort=new AbortController()
    api<{imagery:{context?:{bounds_lat_lon:[[number,number],[number,number]]}}}>('/api/layers',{signal:abort.signal})
      .then(data=>setContext(data.imagery.context?.bounds_lat_lon??null)).catch(()=>{})
    return ()=>abort.abort()
  },[])
  useEffect(()=>{
    if(!host.current)return
    const crs={...L.CRS.EPSG4326,distance:(a:L.LatLng,b:L.LatLng)=>{
      const rad=Math.PI/180,h=Math.sin((b.lat-a.lat)*rad/2)**2+Math.cos(a.lat*rad)*Math.cos(b.lat*rad)*Math.sin((b.lng-a.lng)*rad/2)**2
      return 6792000*Math.asin(Math.sqrt(Math.min(1,h)))
    }}
    const m=L.map(host.current,{crs,center:[15,-100],zoom:1,minZoom:0,maxZoom:18,preferCanvas:true,worldCopyJump:false,maxBounds:[[-90,-180],[90,180]],maxBoundsViscosity:1,attributionControl:true,trackResize:false})
    map.current=m
    L.imageOverlay(assetUrl('/api/assets/mars-global.jpg'),[[-90,-180],[90,180]],{pane:'tilePane',zIndex:0,attribution:'NASA Ames / USGS Viking'}).addTo(m)
    layers.current=L.layerGroup().addTo(m);geologyLayers.current=L.layerGroup().addTo(m)
    terrainLayers.current=L.layerGroup().addTo(m);drawing.current=L.layerGroup().addTo(m)
    m.on('click',(e:L.LeafletMouseEvent)=>callback.current({lon:Math.max(-180,Math.min(180,e.latlng.lng)),lat:Math.max(-90,Math.min(90,e.latlng.lat))}))
    m.on('zoomend',()=>setZoom(m.getZoom()))
    m.on('moveend',()=>{
      const c=m.getCenter();setCentre({lon:c.lng,lat:c.lat})
      const b=m.getBounds()
      setExtent([Math.max(-180,Math.floor(b.getWest()*128)/128),Math.max(-88,Math.floor(b.getSouth()*128)/128),
        Math.min(180,Math.ceil(b.getEast()*128)/128),Math.min(88,Math.ceil(b.getNorth()*128)/128)])
    })
    const element=host.current
    const resize=new ResizeObserver(()=>{
      const previous=m.getSize()
      // Redundant invalidateSize clears Leaflet's exact cached centre, even
      // when nothing resized. A result/disclosure must not cause half-pixel
      // geographic drift. This observer also replaces window resize tracking.
      if(previous.x!==element.clientWidth||previous.y!==element.clientHeight)
        m.invalidateSize({animate:false})
    });resize.observe(element)
    return ()=>{resize.disconnect();m.remove();map.current=null}
  },[])
  useEffect(()=>{
    const m=map.current,group=layers.current
    if(!m||!group)return
    group.clearLayers()
    if(context&&local)group.addLayer(L.imageOverlay(assetUrl('/api/assets/ctx-context.png'),context,{
      pane:'tilePane',zIndex:3,attribution:'USGS CTX regional optical fallback'}))
    const configs=props.layer==='auto'
      ?[props.catalog?.tiles.find(t=>t.id==='viking-hd'),
        ...(previewEnabled&&previewSource?[{...previewSource,max_useful_zoom:6}]:[]),
        ...(sourceId==='hirise-jezero'?[props.catalog?.tiles.find(t=>t.id==='ctx-jezero')]:[]),
        ...(sourceId&&sourceId!=='viking-hd'?[chosen]:[])]
      :[chosen]
    configs.forEach((config,i)=>{
      if(!config)return
      const tiles=L.tileLayer(assetUrl(`/api/atlas/tiles/${config.id}/{z}/{y}/{x}?v=validated-3&fallback=true`),{
        maxNativeZoom:config.max_useful_zoom??config.matrices.length-1,maxZoom:18,tileSize:256,noWrap:true,
        bounds:config.bounds?[[config.bounds[1],config.bounds[0]],[config.bounds[3],config.bounds[2]]]:[[-90,-180],[90,180]],
        zIndex:i===0?2:3+i,keepBuffer:3,updateWhenIdle:false,updateInterval:100,
         attribution:config.id==='ctx-global'?'NASA/JPL/MSSS · Caltech / Esri':'NASA/JPL Mars Trek'})
      group.addLayer(tiles)
    })
  },[props.catalog,props.layer,sourceId,context,local,previewEnabled])
  useEffect(()=>{
    const max=props.layer==='auto'?(local?18:14):chosen?(chosen.max_useful_zoom??chosen.matrices.length-1)+1:4
    map.current?.setMaxZoom(max)
  },[props.layer,local,sourceId])
  const vectorGeology=zoom>=7
  useEffect(()=>{
    if(!props.geology||!vectorGeology||geologicalFeatures)return
    const abort=new AbortController()
    api<FeatureCollection>('/api/atlas/geology',{signal:abort.signal}).then(setGeologicalFeatures).catch(()=>{})
    return ()=>abort.abort()
  },[props.geology,vectorGeology,geologicalFeatures])
  useEffect(()=>{
    const group=terrainLayers.current
    if(!group)return
    group.clearLayers()
    const validation=props.route?.terrain_validation
    if(!validation||!extent||extent[2]-extent[0]>8||extent[3]-extent[1]>8)return
    const [west,south,east,north]=extent
    if(east<=west||north<=south)return
    const params=new URLSearchParams({west:String(west),south:String(south),east:String(east),north:String(north),
      max_grade_deg:String(validation.max_grade_deg)})
    group.addLayer(L.imageOverlay(assetUrl(`/api/hazards/native-slopes?v=rim-guard-1&${params}`),[[south,west],[north,east]],{
      opacity:.75,interactive:false,attribution:`MOLA 128 ppd · slopes > ${validation.max_grade_deg}°`}))
  },[props.route?.terrain_validation,extent])
  useEffect(()=>{
    const group=geologyLayers.current;if(!group)return
    group.clearLayers()
    if(!props.geology)return
    if(vectorGeology&&geologicalFeatures)group.addLayer(L.geoJSON(geologicalFeatures,{
      interactive:false,style:f=>({color:f?.properties?.color??'#aaa',weight:1,fillOpacity:.25}),
      attribution:'USGS SIM 3292 · 1:20M · simplified vector display'}))
    else group.addLayer(L.imageOverlay(assetUrl('/api/assets/global-geology.png'),[[-90,-180],[90,180]],{opacity:.55,interactive:false,attribution:'USGS SIM 3292 · 1:20M'}))
  },[props.geology,vectorGeology,geologicalFeatures])
  useEffect(()=>{
    const group=drawing.current;if(!group)return
    group.clearLayers()
    props.route?.terrain_checks?.forEach(check=>{
      const [west,south,east,north]=check.bounds
      group.addLayer(L.imageOverlay(assetUrl(check.overlay_url),[[south,west],[north,east]],{
        opacity:.7,interactive:false,attribution:`MOLA 128 ppd · slopes > ${check.max_grade_deg}°`}))
    })
    props.route?.hazards?.forEach(crater=>{
      const segments:L.LatLngExpression[][]=[[]]
      craterRing(crater).forEach((p,i,all)=>{
        if(i&&Math.abs(p.lon-all[i-1].lon)>180)segments.push([])
        segments[segments.length-1].push([p.lat,p.lon])
      })
      segments.forEach(line=>{if(line.length>1)group.addLayer(L.polyline(line,{
        color:'#ff7676',weight:1.5,dashArray:'5 4'
      }))})
    })
    const points=[props.start,...props.stops,props.end]
    routeAnchors(props.route,points).forEach(anchor=>{
      if(anchor.offsetM<=.5)return
      splitLongitudeLine([[anchor.actual.lon,anchor.actual.lat],[anchor.snapped.lon,anchor.snapped.lat]])
        .forEach(segment=>group.addLayer(L.polyline(segment.map(p=>[p[1],p[0]] as L.LatLngTuple),{
          color:'#c1c8cf',weight:1.5,dashArray:'2 4',opacity:.85
        })))
      group.addLayer(L.circleMarker([anchor.snapped.lat,anchor.snapped.lon],{
        radius:3,color:'#c1c8cf',weight:1,fillOpacity:.4
      }))
    })
    points.forEach((p,i)=>{
      if(!p)return
      const label=i===0?'A':i===points.length-1?'B':String(i)
      group.addLayer(L.marker([p.lat,p.lon],{icon:L.divIcon({className:'atlas-pin',html:`<span>${label}</span>`,iconSize:[28,28],iconAnchor:[14,14]})}))
    })
    const geometry=props.route?.route?.geometry
    if(geometry?.type==='LineString'){
      const lines=splitLongitudeLine(geometry.coordinates).map(line=>line.map(p=>[p[1],p[0]] as L.LatLngTuple))
      const strategic=strategicRoute(props.route)
      lines.forEach(line=>{if(line.length>1)group.addLayer(L.polyline(line,{
        color:strategic?'#f0b180':'#a4f0d3',weight:3,dashArray:strategic?'8 7':undefined,
        className:strategic?'route-unverified':''}))})
    }
  },[props.start,props.end,props.stops,props.route])
  useEffect(()=>{
    if(!props.focus)return
    const local=Math.abs(props.focus.lon-77.45)<.3&&Math.abs(props.focus.lat-18.44)<.3
    const fine=!!props.route?.terrain_validation||props.route?.terrain_checks?.some(c=>props.focus!.lon>=c.bounds[0]&&props.focus!.lon<=c.bounds[2]
      &&props.focus!.lat>=c.bounds[1]&&props.focus!.lat<=c.bounds[3])
    map.current?.stop().setView([props.focus.lat,props.focus.lon],local?10:fine?9:Math.max(2,Math.min(5,map.current.getZoom())),{animate:false})
  },[props.focus])
  return <div className="atlas-map-shell">
    <div ref={host} className="atlas-map" data-testid="atlas-map" data-source={sourceId??'viking'} data-zoom={zoom} data-view-lon={centre.lon} data-view-lat={centre.lat}/>
    <div className="atlas-map-actions"><button onClick={()=>map.current?.stop().setView([0,0],1,{animate:false})}>Whole planet</button><button onClick={()=>map.current?.stop().setView([18.4447,77.4508],10,{animate:false})}>Jezero</button><button onClick={props.onLocal}>CTX / HiRISE tools</button></div>
    <div className="atlas-map-status" role="status">{chosen?.title??'Viking'} · zoom {zoom}{chosen?` · ${tileSpacing(Math.min(zoom,chosen.matrices.length-1),centre.lat).toFixed(1)} m/px`:''}</div>
  </div>
}
