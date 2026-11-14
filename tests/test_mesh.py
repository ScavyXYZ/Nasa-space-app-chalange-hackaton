"""Verify display meshes only sample observed cells and never bridge NoData."""
import unittest
import numpy as np
from fastapi.testclient import TestClient
from algorithms.mesh import terrain_mesh
from backend.main import create_app
import test_terrain_engine as fixtures


class MeshFixtureTests(unittest.TestCase):
    # Reuse fixture helpers without inheriting/re-running unrelated tests.
    setUp=fixtures.Fixture.setUp
    tearDown=fixtures.Fixture.tearDown
    save=fixtures.Fixture.save
    load=fixtures.Fixture.load
    def test_mesh_source_values_and_holes(self):
        self.z[2,2]=self.slope[2,2]=np.nan;self.mask[2,2]=0;self.save()
        grid=self.load()
        try:
            data=terrain_mesh(grid,max_size=3)
            self.assertEqual(data["sample_rows"],[0,2,4,5])
            width=data["shape"][1]
            for i,row in enumerate(data["sample_rows"]):
                for j,col in enumerate(data["sample_cols"]):
                    actual=data["elevations_m"][i*width+j]
                    if grid.valid[row,col]:
                        self.assertEqual(actual,float(grid.elevation[row,col]))
                    else:
                        self.assertIsNone(actual)
            void_vertex=1*width+1
            self.assertNotIn(void_vertex,data["indices"])
            # All four coarse rectangles touching the void are absent.
            self.assertEqual(len(data["indices"]),30)
        finally:
            grid.close()

    def test_unsampled_void_also_removes_covering_triangles(self):
        self.z[1,1]=self.slope[1,1]=np.nan;self.mask[1,1]=0;self.save()
        grid=self.load()
        try:
            data=terrain_mesh(grid,max_size=3)
            self.assertTrue(all(v is not None for v in data["elevations_m"]))
            self.assertEqual(len(data["indices"]),48)  # One of nine quads omitted.
        finally:
            grid.close()


class MeshAPITests(unittest.TestCase):
    def test_both_real_grids_and_bounded_payloads(self):
        with TestClient(create_app()) as client:
            for name in ("ctx","hirise"):
                response=client.get(f"/api/terrain/mesh?dataset={name}&max_size=80")
                self.assertEqual(response.status_code,200)
                data=response.json()
                self.assertLessEqual(max(data["shape"]),81)
                self.assertEqual(len(data["positions_m"]),len(data["elevations_m"])*3)
                self.assertEqual(len(data["indices"])%3,0)
                self.assertTrue(all(v is not None for v in data["elevations_m"]))
                self.assertTrue(data["indices"])
            self.assertEqual(client.get("/api/terrain/mesh?max_size=1000").status_code,422)


if __name__=="__main__":
    unittest.main()
