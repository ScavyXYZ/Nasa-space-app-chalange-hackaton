import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { ArrowsOut, ArrowsIn, CornersOut, MapTrifold, Path } from '@phosphor-icons/react'
import 'leaflet/dist/leaflet.css'
import type { Bundle, Dataset, Position, Region, RouteResult } from '../types'
import { assetUrl } from '../api'

export const geologyColors = ['#d6ab66','#78b8b1','#b4a1d2','#c7c98a','#9cb4de','#da8d82','#c2a885','#90c5a8','#d68fb5','#cdd6a0','#83b9c6','#dba9d3']
type Props = {
  bundle: Bundle; dataset: Dataset; start: Position | null; end: Position | null
  route: RouteResult | null; visible: Record<string,boolean>; focus: Region | null
  onPick: (position: Position) => void
}
export function MarsMap({ bundle, dataset, start, end, route, visible, focus, onPick }: Props) {
  const host = useRef<HTMLDivElement>(null), mapRef = useRef<L.Map | null>(null)
  const callback = useRef(onPick); callback.current = onPick
  const base = useRef<Record<string,L.Layer>>({})
  const drawing = useRef<L.LayerGroup | null>(null)
  const shell = useRef<HTMLDivElement>(null)
  const [fullscreen,setFullscreen] = useState(false)
  const [viewError,setViewError] = useState('')
  const [cursor, setCursor] = useState('')
  function showArea() {
    const b = bundle.layers.terrain[dataset].metadata?.bounds_lon_lat_deg
    if(b) mapRef.current?.fitBounds([[b[1],b[0]],[b[3],b[2]]],{padding:[24,24]})
  }
  function showRegion() {
    const map=mapRef.current
    const bounds=L.latLngBounds(bundle.layers.imagery.context?.bounds_lat_lon || bundle.layers.imagery.bounds_lat_lon)
    // Use the smallest supported zoom that remains inside real optical coverage.
    map?.setView(bounds.getCenter(),map.getBoundsZoom(bounds,true))
  }
  function showRoute() {
    if(!route?.route || !mapRef.current)return
    const geometry=route.route.geometry
    if(geometry.type==='LineString') {
      mapRef.current.fitBounds(L.latLngBounds(geometry.coordinates.map(c=>[c[1],c[0]] as [number,number])),
        {padding:[70,70],maxZoom:19})
    }else if(geometry.type==='Point') {
      mapRef.current.setView([geometry.coordinates[1],geometry.coordinates[0]],18)
    }
  }
  async function toggleFullscreen() {
    setViewError('')
    try {
      if(document.fullscreenElement===shell.current) await document.exitFullscreen()
      else if(shell.current?.requestFullscreen) await shell.current.requestFullscreen()
      else setViewError('Fullscreen unavailable.')
    }catch{setViewError('Fullscreen unavailable.')}
  }
  useEffect(()=>{
    const change=()=>setFullscreen(document.fullscreenElement===shell.current)
    document.addEventListener('fullscreenchange',change)
    return ()=>document.removeEventListener('fullscreenchange',change)
  },[])
  useEffect(() => {
    const mars = L.extend({}, L.CRS.EPSG4326, { distance(a:L.LatLng,b:L.LatLng) {
      const r = Math.PI/180
      const h = Math.sin((b.lat-a.lat)*r/2)**2 + Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin((b.lng-a.lng)*r/2)**2
      return 2*3396190*Math.asin(Math.sqrt(Math.min(1,h)))
    } }) as L.CRS
    const map = L.map(host.current!, { crs:mars, minZoom:8, maxZoom:22, zoomControl:false,
      zoomSnap:.25,zoomDelta:.5,maxBoundsViscosity:1,
      zoomAnimation:false, fadeAnimation:false })
    mapRef.current = map
    L.control.zoom({position:'topright'}).addTo(map)
    // Control.Scale calls map.distance, which uses the custom Mars sphere above.
    L.control.scale({position:'bottomleft',metric:true,imperial:false,maxWidth:160,updateWhenIdle:false}).addTo(map)
    map.fitBounds(bundle.layers.imagery.bounds_lat_lon)
    const optical = L.layerGroup()
    const context = bundle.layers.imagery.context
    if(context) L.imageOverlay(assetUrl(context.url),context.bounds_lat_lon,{zIndex:0}).addTo(optical)
    L.imageOverlay(assetUrl('/api/assets/ctx-optical.png'), bundle.layers.imagery.bounds_lat_lon,
      {attribution:'NASA/MRO/CTX · USGS Astrogeology',zIndex:1}).addTo(optical)
    base.current.optical = optical
    const availableBounds = L.latLngBounds(context?.bounds_lat_lon || bundle.layers.imagery.bounds_lat_lon)
    map.setMaxBounds(availableBounds)
    const names = bundle.layers.geology.legend.map(x=>x.name)
    base.current.geology = L.geoJSON(bundle.geology, { interactive:false,
      style:f=>({color:geologyColors[Math.max(0,names.indexOf(f?.properties?.name))%geologyColors.length],weight:1.5,fillOpacity:.22}) })
    base.current.science = L.geoJSON(bundle.science, {interactive:false,
      style:{color:'#80d9c8',weight:1,fillOpacity:.03,dashArray:'4 6'} })
    for (const d of ['ctx','hirise','regional'] as const) {
      for (const overlay of bundle.overlays[d]?.overlays || []) {
        base.current[`${d}-${overlay.name}`] = L.imageOverlay(assetUrl(overlay.url),overlay.bounds_lat_lon,{opacity:.76,zIndex:2})
      }
      const bounds = bundle.layers.terrain[d].metadata?.bounds_lon_lat_deg
      if (bounds) base.current[`${d}-bounds`] = L.rectangle([[bounds[1],bounds[0]],[bounds[3],bounds[2]]],
        {color:'#e5b36b',weight:1,fill:false,interactive:false,dashArray:'4 4'})
      if(d==='regional' && bounds)base.current['regional-nodata']=L.imageOverlay(assetUrl('/api/assets/regional-nodata.png'),
        [[bounds[1],bounds[0]],[bounds[3],bounds[2]]],{zIndex:3,interactive:false})
    }
    drawing.current = L.layerGroup().addTo(map)
    map.on('click',e=>callback.current({lon:e.latlng.lng,lat:e.latlng.lat}))
    map.on('mousemove',e=>setCursor(`${e.latlng.lat.toFixed(5)}° N / ${e.latlng.lng.toFixed(5)}° E`))
    function sizeMap() {
      map.invalidateSize()
      map.setMinZoom(map.getBoundsZoom(availableBounds,true))
    }
    sizeMap()
    const observer = new ResizeObserver(sizeMap)
    observer.observe(host.current!)
    return ()=>{ observer.disconnect(); map.remove(); mapRef.current=null }
  }, [bundle])
  useEffect(() => {
    const map = mapRef.current!
    for (const [key,layer] of Object.entries(base.current)) {
      const isTerrain = /-(elevation|slope)$/.test(key)
      const show = (visible[key] && (!isTerrain || key.startsWith(`${dataset}-`))) || key===`${dataset}-bounds` || (dataset==='regional'&&key==='regional-nodata')
      if (show && !map.hasLayer(layer)) map.addLayer(layer)
      if (!show && map.hasLayer(layer)) map.removeLayer(layer)
    }
  }, [visible,dataset,bundle])
  useEffect(() => {
    const b = bundle.layers.terrain[dataset].metadata?.bounds_lon_lat_deg
    if (b) mapRef.current?.fitBounds([[b[1],b[0]],[b[3],b[2]]],{padding:[24,24]})
  }, [dataset,bundle])
  useEffect(() => {
    const group = drawing.current!
    group.clearLayers()
    if (focus) {
      const region = L.geoJSON(focus,{interactive:false,style:{color:'#b5f2d8',weight:3,fillOpacity:.13}}).addTo(group)
      mapRef.current?.fitBounds(region.getBounds(),{padding:[30,30],maxZoom:17})
    }
    if (route?.status==='ok' && route.route) {
      L.geoJSON(route.route,{style:{color:'#f5b079',weight:4,opacity:1},
        pointToLayer:(_,latlng)=>L.circleMarker(latlng,{radius:7,color:'#f5b079'})}).addTo(group)
      if (route.route.geometry.type==='LineString') {
        const coords = route.route.geometry.coordinates
        for (const i of route.metrics?.steep_segment_indices || []) {
          if (coords[i+1]) L.polyline([[coords[i][1],coords[i][0]],[coords[i+1][1],coords[i+1][0]]],
            {color:'#f76969',weight:5}).addTo(group)
        }
      }
    }
    for (const [p,label,color] of [[start,'A','#8ed5c7'],[end,'B','#f5b079']] as const) {
      if(p) L.marker([p.lat,p.lon],{icon:L.divIcon({className:'endpoint-marker',
        html:`<span style="--pin:${color}">${label}</span>`,iconSize:[30,30],iconAnchor:[15,15]})}).addTo(group)
    }
  }, [start,end,route,focus,bundle])
  return <div className="map-shell" ref={shell}>
    <div ref={host} className="mars-map" data-testid="mars-map" aria-label="Jezero map" />
    <div className="map-label"><span className="live-dot" /> JEZERO CRATER <span className="map-label-divider">/</span> {dataset.toUpperCase()}</div>
    <div className="map-view-controls" aria-label="Map view">
      <button type="button" onClick={showArea}><CornersOut size={15} aria-hidden />DEM extent</button>
      <button type="button" onClick={showRegion}><MapTrifold size={15} aria-hidden />Region</button>
      <button type="button" onClick={showRoute} disabled={!route}><Path size={15} aria-hidden />Fit route</button>
      <button type="button" onClick={toggleFullscreen} aria-pressed={fullscreen}>
        {fullscreen?<ArrowsIn size={15} aria-hidden />:<ArrowsOut size={15} aria-hidden />}
        {fullscreen?'Exit fullscreen':'Fullscreen'}
      </button>
    </div>
    {viewError && <div className="map-view-error" role="alert">{viewError}</div>}
    {cursor&&<div className="map-coordinates" aria-live="off">{cursor}</div>}
  </div>
}
