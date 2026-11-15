import type { GlobalRoute } from '../types'

export function strategicRoute(route:GlobalRoute|null|undefined){
  if(route?.terrain_validation?.entire_route)return false
  return route?.traversability?.scope==='strategic_corridor'||route?.dataset==='mola'||route?.approximate===true
}
