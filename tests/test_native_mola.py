import math
import unittest
from unittest.mock import patch

import numpy as np

from algorithms.craters import CraterCatalog
from algorithms.global_routing import GlobalTerrain
from algorithms.mola128 import Mola128Store,NativeMolaPlanner,terrain_slopes,STEP_M
from algorithms.terrain import TerrainError


class FixtureStore(Mola128Store):
    """Local fixture at arbitrary global indices, not special A/B coverage."""
    def __init__(self,heights,origin=(8000,20000)):
        self.heights=np.asarray(heights,dtype=float)
        self.origin=origin
        lats=90-(np.arange(origin[0],origin[0]+heights.shape[0])+.5)/128
        self.slopes=terrain_slopes(self.heights,lats)
    def covered(self,cell):
        r,c=cell[0]-self.origin[0],cell[1]-self.origin[1]
        return 0<=r<self.heights.shape[0] and 0<=c<self.heights.shape[1]
    def values(self,cell):
        local=cell[0]-self.origin[0],cell[1]-self.origin[1]
        return float(self.heights[local]),float(self.slopes[local]),1
    def point(self,r,c):
        return self.coordinate((r+self.origin[0],c+self.origin[1]))
    def local_cell(self,point):
        r,c=self.index(point)
        return r-self.origin[0],c-self.origin[1]


class FixtureGuide:
    step=1/16
    def index(self,point):
        r,c=Mola128Store.index(self,point)
        return r//8,c//8
    def route(self,start,end,*args,**kwargs):
        assert kwargs["avoid_craters"] is False  # Disc exclusion is NOT used.
        return {"status":"ok","expanded_cells":0,
                "route":{"geometry":{"type":"LineString","coordinates":[start,end]}}}
    def _corridor(self,*args):
        class Allowed:
            def __getitem__(self,cell):return True
        return Allowed()


class NativeMolaTests(unittest.TestCase):
    def planner(self,heights,origin=(8000,20000)):
        store=FixtureStore(heights,origin)
        centre=store.point(40,40)
        # Entire fixture lies inside a catalogue crater. That must NOT disable
        # the floor or a low-gradient measured exit.
        craters=CraterCatalog([centre[0]],[centre[1]],[100],buffer_m=0)
        return store,NativeMolaPlanner(store,FixtureGuide(),craters)

    def test_crater_floor_to_floor_is_allowed_inside_catalogue(self):
        h=np.zeros((80,80));h[20:60,20:60]=2000;h[24:56,24:56]=0
        store,planner=self.planner(h)
        result=planner.route(store.point(40,40),store.point(35,35))
        self.assertEqual(result["status"],"ok",result)
        self.assertFalse(result["terrain_validation"]["catalogue_circles_blocked"])
        self.assertTrue(result["terrain_validation"]["entire_route"])

    def test_closed_rim_rejects_exit_despite_equal_endpoint_elevations(self):
        h=np.zeros((80,80));h[20:60,20:60]=2000;h[24:56,24:56]=0
        store,planner=self.planner(h)
        result=planner.route(store.point(40,40),store.point(40,5))
        self.assertEqual(result["status"],"no_route",result)
        self.assertNotIn("route",result)

    def test_exit_uses_gap_not_steep_rim_for_unrelated_world_locations(self):
        for origin in [(8000,20000),(15000,40000)]:
            h=np.zeros((80,80));h[20:60,20:60]=2000;h[24:56,24:56]=0
            h[54:61,35:45]=0
            store,planner=self.planner(h,origin)
            result=planner.route(store.point(40,40),store.point(40,5))
            self.assertEqual(result["status"],"ok",result)
            coords=result["route"]["geometry"]["coordinates"]
            cells=[store.local_cell(p) for p in coords]
            self.assertGreaterEqual(max(r for r,c in cells),60)
            self.assertTrue(all(store.slopes[cell]<=15 for cell in cells))
            self.assertLessEqual(result["metrics"]["max_grade_deg"],15)
            self.assertLessEqual(result["metrics"]["max_surface_slope_deg"],15)

    def test_single_cell_summit_cannot_hide_in_central_derivative(self):
        h=np.zeros((15,15));h[7,7]=1500
        self.assertEqual(np.gradient(h)[0][7,7],0)
        self.assertGreater(terrain_slopes(h,np.zeros(15))[7,7],70)

    def test_gradual_high_altitude_slope_remains_allowed(self):
        h=np.repeat((np.arange(80)*10.)[:,None],80,axis=1)+15000
        store,planner=self.planner(h)
        result=planner.route(store.point(20,20),store.point(60,60))
        self.assertEqual(result["status"],"ok",result)

    def test_endpoint_on_rim_is_rejected_not_entire_crater(self):
        h=np.zeros((80,80));h[20:60,20:60]=2000;h[24:56,24:56]=0
        store,planner=self.planner(h)
        result=planner.route(store.point(20,40),store.point(40,40))
        self.assertEqual(result["status"],"blocked_endpoint")
        self.assertEqual(result["reason"],"native_surface_slope")

    def test_missing_source_does_not_fall_back_to_coarse_route(self):
        store,planner=self.planner(np.zeros((80,80)))
        with patch.object(store,"values",side_effect=TerrainError("terrain_data_unavailable","Missing",503)):
            with self.assertRaises(TerrainError):
                planner.route(store.point(40,40),store.point(35,35))

    def test_indexing_wraps_and_native_grid_has_real_spacing(self):
        store=Mola128Store()
        self.assertEqual(store.index((-180,10)),store.index((180,10)))
        self.assertAlmostEqual(STEP_M,463.05766717,places=6)
        self.assertFalse(store.covered(store.index((0,89))))

    def test_real_gale_crater_floor_is_routable(self):
        store=Mola128Store();guide=GlobalTerrain.load()
        a,b=(137.4,-4.6),(137.45,-4.6)
        self.assertTrue(guide.hazards.containing(a))
        self.assertTrue(guide.hazards.containing(b))
        result=NativeMolaPlanner(store,guide,guide.hazards).route(a,b)
        self.assertEqual(result["status"],"ok",result)
        self.assertTrue(result["terrain_validation"]["entire_route"])
        self.assertLessEqual(result["metrics"]["max_surface_slope_deg"],15)
        self.assertTrue(all(p["dataset"]=="mola128" for p in result["profile"]))

    def test_official_heights_and_cross_tile_seams(self):
        store=Mola128Store()
        self.assertEqual(store.sample((-97.150761,24.024217))["elevation_m"],6606)
        self.assertEqual(store.sample((150.624967,9.070396))["elevation_m"],-2705)
        for lon,lat in [(0,44),(90,0),(180,-44),(-.001,0),(0,60),(0,-60)]:
            sample=store.sample((lon,lat))
            self.assertTrue(sample["valid"],(lon,lat,sample))
            self.assertTrue(math.isfinite(sample["slope_deg"]))

    def test_stationary_native_cell_is_valid(self):
        store,planner=self.planner(np.zeros((80,80)))
        p=store.point(40,40)
        result=planner.route(p,p)
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["route"]["geometry"]["type"],"Point")
        self.assertEqual(result["metrics"]["distance_m"],0)


if __name__=="__main__":unittest.main()
