import unittest
import numpy as np

from algorithms.craters import CraterCatalog
from algorithms.global_routing import GlobalTerrain,distance
from algorithms.fine_mola import FineMolaPatch,refine_global_result


class CraterHazardTests(unittest.TestCase):
    def test_segment_cannot_jump_over_small_crater_between_valid_vertices(self):
        craters=CraterCatalog([0],[0],[20],ids=["rim"],buffer_m=0)
        self.assertFalse(craters.containing((-1,0)))
        self.assertFalse(craters.containing((1,0)))
        self.assertEqual(craters.intersections((-1,0),(1,0)),["rim"])
        self.assertFalse(craters.intersections((-1,1),(1,1)))

    def test_dateline_and_pole_use_spherical_arcs(self):
        craters=CraterCatalog([180,0],[0,90],[20,20],ids=["seam","pole"],buffer_m=0)
        self.assertIn("seam",craters.intersections((179,0),(-179,0)))
        self.assertIn("pole",craters.intersections((0,89),(180,89)))

    def test_flat_dem_route_actually_detours_around_catalogue(self):
        grid=GlobalTerrain(np.zeros((24,48)),np.ones((24,48)))
        a=grid.coordinate((12,20));b=grid.coordinate((12,24))
        left=grid.coordinate((12,21));right=grid.coordinate((12,22))
        centre=((left[0]+right[0])/2,(left[1]+right[1])/2)
        catalogue=CraterCatalog([centre[0]],[centre[1]],[100],buffer_m=0)
        grid.hazards=catalogue
        baseline=grid.route(a,b,avoid_craters=False)
        detour=grid.route(a,b)
        self.assertEqual(detour["status"],"ok")
        self.assertGreater(detour["metrics"]["distance_m"],baseline["metrics"]["distance_m"])
        line=detour["route"]["geometry"]["coordinates"]
        self.assertTrue(all(not catalogue.intersections(x,y) for x,y in zip(line,line[1:])))
        self.assertTrue(detour["hazard_policy"]["enabled"])

    def test_endpoint_inside_catalogue_is_not_given_an_invented_exit(self):
        grid=GlobalTerrain(np.zeros((24,48)),np.ones((24,48)))
        a=grid.coordinate((12,20))
        grid.hazards=CraterCatalog([a[0]],[a[1]],[100])
        result=grid.route(a,grid.coordinate((12,24)))
        self.assertEqual(result["status"],"blocked_endpoint")
        self.assertEqual(result["reason"],"crater_exclusion")
        self.assertNotIn("route",result)

    def test_real_finer_mola_preserves_source_values_and_detects_steep_cells(self):
        patches=FineMolaPatch.load_all()
        self.assertEqual(len(patches),2)
        patch=next(p for p in patches if p.metadata["id"]=="a")
        sample=patch.sample((-97.150761,24.024217))
        self.assertEqual(sample["elevation_m"],6606)
        self.assertLess(sample["spacing_m"],464)
        self.assertGreater(float(patch.slope.max()),35)
        self.assertTrue((patch.counts==0).any())  # Do not hide interpolation.

    def test_closed_rim_blocks_exit_but_gradual_climb_is_allowed(self):
        heights=np.zeros((40,40))
        heights[10:30,10:30]=10000
        heights[13:27,13:27]=0
        meta={"id":"test","bounds":[0,0,40/128,40/128],"ppd":128,"source":"fixture"}
        patch=FineMolaPatch(heights,np.ones_like(heights),meta)
        result=patch.exit_check(patch.pixel_to_lonlat(20,20),15)
        self.assertEqual(result["status"],"no_route")
        smooth=np.repeat((np.arange(40)*10.)[:,None],40,axis=1)+100000
        patch=FineMolaPatch(smooth,np.ones_like(smooth),meta)
        self.assertEqual(patch.exit_check(patch.pixel_to_lonlat(20,20),15)["status"],"ok")

    def test_refinement_uses_a_real_low_gradient_gap_instead_of_crossing_rim(self):
        h=np.zeros((80,80));h[20:60,20:60]=10000;h[24:56,24:56]=0
        h[54:61,35:45]=0
        patch=FineMolaPatch(h,np.ones_like(h),{
            "id":"test","bounds":[0,0,80/128,80/128],"ppd":128,"source":"fixture"})
        a=patch.pixel_to_lonlat(40,40);b=patch.pixel_to_lonlat(40,5)
        baseline={"status":"ok","expanded_cells":0,
                  "route":{"type":"Feature","geometry":{"type":"LineString","coordinates":[a,b]},"properties":{}},
                  "profile":[{"elevation_m":0,"interpolated":False},{"elevation_m":0,"interpolated":False}],
                  "metrics":{"distance_m":distance(a,b)},"traversability":{"terrain_constraints_checked":[]}}
        result=refine_global_result(baseline,a,b,[patch],15,5)
        self.assertEqual(result["status"],"ok",result)
        line=result["route"]["geometry"]["coordinates"]
        self.assertGreater(len(line),40)
        cells=[patch.lonlat_to_pixel(*p) for p in line]
        self.assertGreater(max(r for r,c in cells),55)  # It exits via the gap.
        self.assertTrue(all(patch.slope[c]<=15 for c in cells))
        self.assertLessEqual(result["metrics"]["max_grade_deg"],15)


if __name__=="__main__":unittest.main()
