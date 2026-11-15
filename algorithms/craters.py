"""Catalogue footprint exclusion with exact spherical segment/cap intersection.

Published circle fits are an exclusion policy, NOT measured impassable rims.
Unknown small craters/cliffs remain outside this catalogue's guarantees.
"""
import hashlib
import json
import math

import numpy as np
from shapely import STRtree, box
from shapely.geometry import Point

from .terrain import ROOT, TerrainError

RADIUS=3396000.


def unit(point):
    lon,lat=map(math.radians,point)
    return np.array([math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)])


class CraterCatalog:
    def __init__(self,lon,lat,diameter_km,ids=None,names=None,metadata=None,buffer_m=100):
        self.lon=np.asarray(lon,dtype=float);self.lat=np.asarray(lat,dtype=float)
        self.diameter=np.asarray(diameter_km,dtype=float)
        if (self.lon.shape!=self.lat.shape or self.lon.shape!=self.diameter.shape
            or not np.isfinite(np.c_[self.lon,self.lat,self.diameter]).all()
            or np.any(np.abs(self.lat)>90) or np.any(self.diameter<=0)):
            raise ValueError("Invalid crater catalogue")
        self.ids=np.asarray(ids if ids is not None else [str(i) for i in range(len(self.lon))])
        self.names=np.asarray(names if names is not None else [""]*len(self.lon))
        self.metadata=metadata or {}
        self.buffer_m=buffer_m
        self.radii=self.diameter*500+buffer_m
        angles=self.radii/RADIUS
        self.cos_radius=np.cos(angles)
        lon_r=np.radians(self.lon);lat_r=np.radians(self.lat)
        self.centres=np.c_[np.cos(lat_r)*np.cos(lon_r),np.cos(lat_r)*np.sin(lon_r),np.sin(lat_r)]
        dy=np.degrees(angles)
        dx=np.degrees(np.arcsin(np.minimum(1,np.sin(angles)/np.maximum(1e-15,np.cos(lat_r)))))
        dx=np.where(np.abs(self.lat)+dy>=90,180,dx)
        west=self.lon-dx;east=self.lon+dx
        south=np.maximum(-90,self.lat-dy);north=np.minimum(90,self.lat+dy)
        # Duplicated boxes, not duplicated scientific records, handle ±180°.
        boxes=[box(west,south,east,north)]
        mapping=[np.arange(len(self.lon))]
        for shift,mask in [(360,west< -180),(-360,east>180)]:
            boxes.append(box(west[mask]+shift,south[mask],east[mask]+shift,north[mask]))
            mapping.append(np.flatnonzero(mask))
        self.mapping=np.concatenate(mapping)
        self.tree=STRtree(np.concatenate(boxes))

    @classmethod
    def load(cls,root=ROOT):
        folder=root/"data/processed/craters"
        try:
            metadata=json.loads((folder/"metadata.json").read_text(encoding="utf-8"))
            path=folder/"robbins.npz"
            if hashlib.sha256(path.read_bytes()).hexdigest()!=metadata["runtime_sha256"]:
                raise ValueError("Crater catalogue checksum mismatch")
            with np.load(path,allow_pickle=False) as data:
                return cls(data["lon"],data["lat"],data["diameter_km"],data["ids"],data["names"],metadata)
        except (OSError,ValueError,KeyError) as exc:
            raise TerrainError("craters_unavailable","Prepare the real crater catalogue first",503) from exc

    def describe(self,index):
        i=int(index)
        return {"id":str(self.ids[i]),"name":str(self.names[i]),"lon":float(self.lon[i]),"lat":float(self.lat[i]),
                "diameter_km":float(self.diameter[i]),"exclusion_radius_m":float(self.radii[i]),
                "geometry_model":"published circle fit + 100 m conservative planning buffer",
                "source":self.metadata.get("source","https://craters.sjrdesign.net/")}

    def containing(self,point):
        indices=np.unique(self.mapping[self.tree.query(Point(*point))])
        if not len(indices):return []
        hits=indices[self.centres[indices]@unit(point)>=self.cos_radius[indices]-1e-14]
        return [self.describe(i) for i in hits]

    def intersections(self,a,b,*,rim_only=False):
        lon_b=a[0]+((b[0]-a[0]+180)%360-180)
        indices=None
        # Cheap conservative broad phase for native, sub-degree grid edges.
        # The 0.001° pad exceeds their great-circle latitude bulge below 88°.
        # Exact spherical tests still decide every candidate intersection.
        if abs(lon_b-a[0])<.1 and abs(a[1]-b[1])<.1 and max(abs(a[1]),abs(b[1]))<88:
            indices=np.unique(self.mapping[self.tree.query(box(min(a[0],lon_b),min(a[1],b[1])-.001,
                                                               max(a[0],lon_b),max(a[1],b[1])+.001))])
            if not len(indices):return []
        va,vb=unit(a),unit(b)
        dot=float(np.clip(va@vb,-1,1));angle=math.acos(dot)
        if angle<1e-12:return [] if rim_only else [h["id"] for h in self.containing(a)]
        if angle>math.pi-1e-8:
            raise ValueError("Antipodal arc is ambiguous; split the edge")
        tangent=(vb-dot*va)/math.sin(angle)
        lats=[a[1],b[1]]
        critical=math.atan2(tangent[2],va[2])
        for t in [critical,critical+math.pi,critical-math.pi]:
            if 0<t<angle:lats.append(math.degrees(math.asin(np.clip(va[2]*math.cos(t)+tangent[2]*math.sin(t),-1,1))))
        west,east=sorted([a[0],lon_b])
        if max(lats)>89.999999 or min(lats)<-89.999999:west,east=-180,180
        if indices is None:
            indices=np.unique(self.mapping[self.tree.query(box(west,min(lats)-1e-9,east,max(lats)+1e-9))])
        if not len(indices):return []
        centres=self.centres[indices]
        normal=np.cross(va,vb);normal/=np.linalg.norm(normal)
        normal_dot=centres@normal
        projected=centres-normal_dot[:,None]*normal
        norm=np.linalg.norm(projected,axis=1)
        projected/=np.maximum(norm[:,None],1e-15)
        along=np.arctan2(projected@tangent,projected@va)
        inside=(along>=-1e-12)&(along<=angle+1e-12)
        nearest_dot=np.where(inside,norm,np.maximum(centres@va,centres@vb))
        hits=indices[nearest_dot>=self.cos_radius[indices]-1e-14]
        if rim_only and len(hits):
            # A spherical cap (< hemisphere) is geodesically convex: two
            # strictly interior endpoints do not cross its boundary.
            entirely_inside=(self.centres[hits]@va>self.cos_radius[hits]+1e-14)&(
                self.centres[hits]@vb>self.cos_radius[hits]+1e-14)
            hits=hits[~entirely_inside]
        return [str(self.ids[int(i)]) for i in hits]

    def policy(self):
        return {"enabled":True,"catalogue":self.metadata.get("title","Crater circle catalogue"),
                "records":len(self.lon),"minimum_diameter_km":self.metadata.get("minimum_diameter_km"),
                "buffer_m":self.buffer_m,"source":self.metadata.get("source"),
                "rule":"Do not cross catalogue crater footprints; start/end inside require a locally verified exit.",
                "limitations":"Circle fits are not exact rim polygons or proof of physical impassability. Missing craters and cliffs remain unknown."}

    def nearby(self,point,radius_m=100000,limit=80):
        delta=math.degrees(radius_m/RADIUS)
        dx=min(180,delta/max(.01,math.cos(math.radians(point[1]))))
        indices=np.unique(self.mapping[self.tree.query(box(point[0]-dx,max(-90,point[1]-delta),
                                                           point[0]+dx,min(90,point[1]+delta)))])
        if not len(indices):return []
        distances=np.arccos(np.clip(self.centres[indices]@unit(point),-1,1))*RADIUS-self.radii[indices]
        selected=indices[np.argsort(distances)]
        return [self.describe(i) for i in selected[:limit] if
                math.acos(float(np.clip(self.centres[i]@unit(point),-1,1)))*RADIUS-self.radii[i]<=radius_m]
