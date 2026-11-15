import type { Bundle, Layers, Regions } from './types'

const origin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const assetUrl = (path: string) => `${origin}${path}`
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(assetUrl(path), options)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    const messages:Record<string,string>={
      invalid_coordinate:'Invalid coordinates.',invalid_parameters:'Invalid parameters.',
      outside_coverage:'Outside DEM coverage.',server_busy:'Server busy.',
      terrain_data_unavailable:'Terrain data unavailable.',terrain_data_invalid:'Invalid terrain data.',
      craters_unavailable:'Crater data unavailable.',dataset_unavailable:'Dataset unavailable.',
      global_unavailable:'MOLA data unavailable.',geology_unavailable:'Geology data unavailable.',
      route_nodata:'The route crosses missing data.',profile_too_large:'Profile limit reached.',
      imagery_unavailable:'Imagery unavailable.',tile_unavailable:'Imagery unavailable.',
    }
    const message=data?.detail?.message
    throw new Error(messages[data?.detail?.code]||
      (typeof message==='string'&&message.length<180&&!/\p{Script=Cyrillic}/u.test(message)?message:
        response.status===422?'Invalid coordinates or parameters.':`Request failed (${response.status}).`))
  }
  return response.json()
}
export async function loadBundle(signal: AbortSignal): Promise<Bundle> {
  const layers=await api<Layers>('/api/layers',{signal})
  const [science,geology]=await Promise.all([
    api<Regions>(layers.science.url,{signal}),api<Bundle['geology']>(layers.geology.url,{signal}),
  ])
  const overlays: Bundle['overlays'] = {}
  await Promise.all((['ctx','hirise','regional'] as const).filter(d => layers.terrain[d]?.available).map(async d => {
    try{overlays[d] = await api(`/api/overlays/${d}`, { signal })}
    catch(e){if(e instanceof Error&&e.name==='AbortError')throw e}
  }))
  return { layers, science, geology, overlays }
}
