import type { GlobalRoute } from '../types'

export function strategicRoute(route:GlobalRoute|null|undefined){
  if(route?.terrain_validation?.entire_route)return false
  return route?.traversability?.scope==='strategic_corridor'||route?.dataset==='mola'||route?.approximate===true
}

export function traversabilityNotice(route:GlobalRoute){
  return route.traversability?.message??(strategicRoute(route)
    ?'Лише стратегічний напрямок — прохідність не перевірена. Лінія може перетинати борти кратерів і непроїзні уступи, яких не розрізняє глобальна DEM.'
    :'Шлях у локальній DEM, не підтверджена прохідність. Каміння, ґрунт і зчеплення не перевірені.')
}
