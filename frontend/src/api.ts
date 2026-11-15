import type { Bundle, Layers, Regions } from './types'

const origin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
export const assetUrl = (path: string) => `${origin}${path}`
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(assetUrl(path), options)
  if (!response.ok) {
    const data = await response.json().catch(() => null)
    throw new Error(data?.detail?.message || (response.status===422?'Перевірте координати, зупинки та параметри моделі.':`API недоступний (${response.status}). Перевірте сервер і дані.`))
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
