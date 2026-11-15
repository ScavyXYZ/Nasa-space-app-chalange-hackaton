"""Regressions for known craters hidden by smooth/interpolated MOLA bins."""
import unittest
from unittest.mock import patch

import numpy as np

from algorithms.craters import CraterCatalog
from algorithms.mola128 import Mola128Store,NativeMolaPlanner,STEPS
from algorithms.rim_guard import CatalogueRimGuard
from test_native_mola import FixtureStore,FixtureGuide


class RimGuardTests(unittest.TestCase):
    def model(self,diameter=1.21,origin=(8000,20000)):
        store=FixtureStore(np.zeros((80,80)),origin)
        centre=store.point(40,40)
        catalogue=CraterCatalog([centre[0]],[centre[1]],[diameter],ids=["known"],buffer_m=100)
        return store,catalogue,NativeMolaPlanner(store,FixtureGuide(),catalogue)

    def test_flat_dem_does_not_override_known_small_crater(self):
        store,catalogue,planner=self.model()
        a,b=store.point(40,30),store.point(40,50)
        self.assertEqual(catalogue.intersections(a,b),["known"])
        result=planner.route(a,b)
        self.assertEqual(result["status"],"ok",result)
        self.assertTrue(result["terrain_validation"]["catalogue_rim_guard"])
        self.assertEqual(result["metrics"]["max_grade_deg"],0)
        coordinates=result["route"]["geometry"]["coordinates"]
        self.assertTrue(all(not catalogue.intersections(x,y) for x,y in zip(coordinates,coordinates[1:])))
        self.assertTrue(any(store.local_cell(p)[0]!=40 for p in coordinates))

    def test_floor_to_floor_stays_allowed(self):
        store,catalogue,planner=self.model(diameter=8)
        a,b=store.point(38,38),store.point(42,42)
        self.assertEqual(catalogue.containing(a)[0]["id"],"known")
        self.assertEqual(catalogue.containing(b)[0]["id"],"known")
        self.assertEqual(catalogue.intersections(a,b,rim_only=True),[])
        self.assertEqual(planner.route(a,b)["status"],"ok")

    def test_flat_dem_is_not_an_exit_certificate(self):
        store,_,planner=self.model(diameter=8)
        result=planner.route(store.point(40,40),store.point(40,60))
        self.assertEqual(result["status"],"no_route")
        self.assertEqual(result["reason"],"crater_exit_needs_finer_dem")
        self.assertNotIn("route",result)

    def test_independent_final_check_rejects_a_broken_raster_guard(self):
        store,_,planner=self.model()
        with patch.object(planner.rims,"blocked",return_value=False):
            result=planner.route(store.point(40,30),store.point(40,50))
        self.assertEqual(result["status"],"no_route")
        self.assertEqual(result["reason"],"rim_validation_failed")
        self.assertNotIn("route",result)

    def test_anchor_on_uncertain_rim_has_specific_failure(self):
        store,_,planner=self.model(diameter=8)
        # Nine north/south cells are ~4.17 km from the 4 km fitted radius.
        result=planner.route(store.point(49,40),store.point(60,40))
        self.assertEqual(result["status"],"blocked_endpoint")
        self.assertEqual(result["reason"],"unresolved_catalogue_rim")

    def test_no_open_neighbour_edge_can_jump_rim_including_diagonals(self):
        for origin in [(8000,20000),(11500,23000),(300,23000)]:
            store,catalogue,planner=self.model(diameter=1.21,origin=origin)
            for r in range(28,53):
                for c in range(28,53):
                    a=(origin[0]+r,origin[1]+c)
                    if planner.rims.blocked(a):continue
                    for dr,dc in STEPS:
                        b=(a[0]+dr,(a[1]+dc)%store.cols)
                        if planner.rims.blocked(b):continue
                        self.assertFalse(catalogue.intersections(store.coordinate(a),store.coordinate(b),rim_only=True),
                                         (origin,a,b))

    def test_window_matches_block_across_date_line_and_prime_meridian(self):
        store=Mola128Store()
        for lon in [179.999,-179.999,-.001,.001]:
            catalogue=CraterCatalog([lon],[10],[1.21])
            guard=CatalogueRimGuard(catalogue)
            r,c=store.index((lon,10))
            mask=guard.window(r-8,r+9,c-8,c+9)
            for dr in range(-8,9):
                for dc in range(-8,9):
                    self.assertEqual(bool(mask[dr+8,dc+8]),guard.blocked((r+dr,(c+dc)%store.cols)))

    def test_rim_intersection_handles_between_vertex_crater_and_date_line(self):
        catalogue=CraterCatalog([180],[0],[1.21],ids=["seam"])
        self.assertEqual(catalogue.intersections((179.98,0),(-179.98,0),rim_only=True),["seam"])
        self.assertEqual(catalogue.intersections((179.999,0),(-179.999,0),rim_only=True),[])


if __name__=="__main__":unittest.main()
