import type { Feature, FeatureCollection, Geometry } from 'geojson'

export type Dataset = 'ctx' | 'hirise' | 'regional'
export type Position = { lon: number; lat: number }
export type GlobalTerrainData = {
  shape: [number,number]; latitudes: number[]; longitudes: number[]; elevations_m: number[]
  title: string; source_page: string; texture_url: string; resolution_deg: number
  equatorial_spacing_m: number
  height_range_m: [number,number]; observed_fraction: number; radius_m: number
}
export type GlobalRoute = {
  status: 'ok'|'no_route'|'search_limit'|'blocked_endpoint'|'outside_grid'; dataset?: 'mola'|'mola128'|'regional'|'hirise'; approximate?: boolean
  route?: Feature; elapsed_ms?: number; expanded_cells: number; warnings?: string[]
  traversability?: {status:'unverified';scope:'strategic_corridor'|'local_dem_path';dem_spacing_m:number;message:string}
  message?:string;reason?:string
  hazard_policy?:{enabled:boolean;mode?:string;records?:number;source?:string;rule?:string}
  terrain_validation?:{spacing_m:number;max_grade_deg:number;entire_route:boolean;catalogue_circles_blocked:boolean;catalogue_rim_guard?:boolean;model?:string}
  hazards?:CraterHazard[]
  terrain_checks?:FineTerrainCheck[]
  metrics?: {distance_m:number;direct_distance_m:number;min_elevation_m:number;max_elevation_m:number
    ascent_m:number;descent_m:number;max_grade_deg:number;max_surface_slope_deg?:number;interpolated_cells:number;cells:number;snap_offsets_m:number[]}
  profile?: {distance_m:number;elevation_m:number;interpolated:boolean;dataset?:string}[]
  legs?: {index:number;distance_m:number;ascent_m:number;max_grade_deg:number;start:number[];end:number[]}[]
  geological_units?: GeologicalUnit[]
  data_quality?: {resolution_deg:number;equatorial_spacing_m:number;vertical_datum:string;source:string;product:string}
}
export type CraterHazard={id:string;name:string;lon:number;lat:number;diameter_km:number;exclusion_radius_m:number;source:string}
export type FineTerrainCheck={id:string;bounds:[number,number,number,number];spacing_m:number;max_grade_deg:number;source:string;overlay_url:string;status?:string;interpolated_fraction:number}
export type GeologicalUnit={id:number;unit:string;description:string;color:string;source:string}
export type AtlasCatalog={
  source:string;features:number;units:number;scale:string
  tiles:{id:string;title:string;matrices:string[];note:string;source:string;bounds?:number[];nominal_m_per_pixel?:number;appearance?:string;max_useful_zoom?:number;native_tile_size?:number}[]
  legend:GeologicalUnit[]
  missions:{id:string;title:string;description:string;credit:string;source:string;url:string;region:string;lon:number;lat:number;location_note:string}[]
}
export type Region = Feature<Geometry, {
  name: string; description: string; research_interest: string; source: string
  registration_warning: string; distance_to_route_m?: number; route_intersects_region?: boolean
}>
export type Regions = FeatureCollection<Geometry, Region['properties']>
export type Overlay = {
  name: string; url: string; bounds_lat_lon: [[number, number], [number, number]]
  legend: { units: string; min: number; max: number; colormap: string }
}
export type Layers = {
  terrain: Record<Dataset, { available: boolean; metadata?: {
    bounds_lon_lat_deg: [number,number,number,number]; shape_rows_cols: [number,number]
    pixel_size_m: [number,number]
    valid_fraction?: number; extent_projected_km?:[number,number]
  } }>
  imagery: {
    bounds_lat_lon: [[number,number],[number,number]]; source: string
    context?: {url:string; bounds_lat_lon:[[number,number],[number,number]]; coverage_note:string}
  }
  geology: { url:string; legend: { name: string; symbols: string[]; source: string }[]; source: string }
  science: {url:string}
}
export type Bundle = {
  layers: Layers; science: Regions; geology: FeatureCollection
  overlays: Partial<Record<Dataset, { overlays: Overlay[] }>>
}
export type Sample = { valid: boolean; elevation_m: number | null; slope_deg: number | null }
export type TerrainMeshData = {
  dataset: Dataset; shape:[number,number]; source_shape:[number,number]
  sample_rows:number[]; sample_cols:number[]; stride:number
  longitudes:number[]; latitudes:number[]; positions_m:number[]; elevations_m:(number|null)[]
  slopes_deg:(number|null)[]
  indices:number[]; origin_lon_lat:[number,number]; elevation_origin_m:number
  elevation_range_m:[number,number]; radius_m:number; note:string
}
export type RouteResult = {
  status: 'ok' | 'no_route' | 'outside_grid' | 'blocked_endpoint' | 'search_limit'
  dataset: Dataset; endpoint?: string; route?: Feature; snapped_start?: [number,number]; snapped_end?: [number,number]
  nearby_science: Region[]; expanded_cells?: number; cost?: number
  parameters: { max_slope_deg: number; slope_weight: number; nearby_radius_m: number }
  metrics?: {
    distance_m: number; min_elevation_m: number; max_elevation_m: number; ascent_m: number; descent_m: number
    max_slope_deg: number; max_segment_grade_deg: number; steep_segment_indices: number[]
    elevation_profile: { distance_m: number; elevation_m: number; slope_deg: number }[]
  }
}
