"""Proximity of a route to sourced REGIONS, in projected Mars metres."""
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform


def nearby_regions(route_geometry, collection, terrain, radius_m=200):
    projection = Transformer.from_crs(terrain.crs.geodetic_crs,terrain.crs,always_xy=True)
    route = transform(projection.transform,shape(route_geometry))
    found = []
    for feature in collection["features"]:
        region = transform(projection.transform,shape(feature["geometry"]))
        distance = float(route.distance(region))
        if distance <= radius_m:
            found.append({**feature,"properties":{**feature["properties"],
                          "distance_to_route_m":distance,"route_intersects_region":bool(route.intersects(region))}})
    return sorted(found,key=lambda f:f["properties"]["distance_to_route_m"])
