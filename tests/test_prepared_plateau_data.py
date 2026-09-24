from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kage_michi.infrastructure.plateau_prepared import (
    BUILDINGS_FILE,
    MANIFEST_FILE,
    PlateauPreparationConfig,
    load_prepared_plateau_buildings,
    mesh_codes_for_radius,
    prepare_plateau_buildings,
    third_mesh_code,
)
from kage_michi.models import GeoPoint


GML = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel
 xmlns:core="http://www.opengis.net/citygml/2.0"
 xmlns:gml="http://www.opengis.net/gml"
 xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
 xmlns:uro="https://www.geospatial.jp/iur/uro/3.1">
 <gml:boundedBy>
  <gml:Envelope srsName="http://www.opengis.net/def/crs/EPSG/0/6697"
                srsDimension="3">
   <gml:lowerCorner>34.23 135.19 4</gml:lowerCorner>
   <gml:upperCorner>34.24 135.20 16</gml:upperCorner>
  </gml:Envelope>
 </gml:boundedBy>
 <core:cityObjectMember>
  <bldg:Building gml:id="bldg-1">
   <bldg:measuredHeight uom="m">12.5</bldg:measuredHeight>
   <uro:lod1HeightType>中央値</uro:lod1HeightType>
   <bldg:lod1Solid>
    <gml:Solid><gml:exterior><gml:CompositeSurface>
     <gml:surfaceMember><gml:Polygon gml:id="floor">
      <gml:exterior><gml:LinearRing>
       <gml:posList srsDimension="3">34.2324 135.1916 4 34.2324 135.1918 4 34.2326 135.1918 4 34.2326 135.1916 4 34.2324 135.1916 4</gml:posList>
      </gml:LinearRing></gml:exterior>
     </gml:Polygon></gml:surfaceMember>
     <gml:surfaceMember><gml:Polygon gml:id="roof">
      <gml:exterior><gml:LinearRing>
       <gml:posList srsDimension="3">34.2324 135.1916 16 34.2324 135.1918 16 34.2326 135.1918 16 34.2326 135.1916 16 34.2324 135.1916 16</gml:posList>
      </gml:LinearRing></gml:exterior>
     </gml:Polygon></gml:surfaceMember>
    </gml:CompositeSurface></gml:exterior></gml:Solid>
   </bldg:lod1Solid>
  </bldg:Building>
 </core:cityObjectMember>
</core:CityModel>
"""


class PreparedPlateauDataTests(unittest.TestCase):
    def create_source(self, root: Path, content: str = GML) -> Path:
        source = root / "citygml.zip"
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("udx/bldg/51352175_bldg_6697_op.gml", content)
            archive.writestr("udx/bldg/51352176_bldg_6697_op.gml", content.replace("bldg-1", "bldg-2"))
            archive.writestr("udx/dem/51352175_dem_6697_op.gml", content)
        return source

    def config(self) -> PlateauPreparationConfig:
        return PlateauPreparationConfig(
            center=GeoPoint(34.2325, 135.1917),
            radius_m=100,
            mesh_codes=("51352175",),
        )

    def test_mesh_code_and_radius_selection_include_station(self) -> None:
        self.assertEqual(third_mesh_code(34.2325, 135.1917), "51352175")
        meshes = mesh_codes_for_radius(GeoPoint(34.2325, 135.1917), 1_700)
        self.assertIn("51352175", meshes)
        self.assertGreater(len(meshes), 1)

    def test_prepare_and_load_extracts_lod1_without_height_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "prepared"
            prepare_plateau_buildings(self.create_source(root), output, self.config())
            prepared = load_prepared_plateau_buildings(output)
            manifest = prepared.manifest
            building = prepared.buildings.iloc[0]

        self.assertEqual(len(prepared.buildings), 1)
        self.assertEqual(building["building_id"], "bldg-1")
        self.assertAlmostEqual(building["height_m"], 12.0)
        self.assertAlmostEqual(building["measured_height_m"], 12.5)
        self.assertEqual(building["lod1_height_type"], "中央値")
        self.assertEqual(building["source_mesh"], "51352175")
        self.assertEqual(str(prepared.buildings.crs), "EPSG:6676")
        self.assertEqual(manifest.counts["citygml_files"], 1)
        self.assertEqual(manifest.counts["missing_height"], 0)
        self.assertGreater(manifest.source_bytes, 0)
        self.assertIn("plateau.reearth.io", manifest.source_url)
        self.assertIn("parse_filter_seconds", manifest.metrics)
        self.assertGreater(manifest.metrics["peak_memory_bytes"], 0)
        self.assertIn("EPSG/0/6697", manifest.source_crs[0])

    def test_same_input_reproduces_semantic_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.create_source(root)
            first = root / "first"
            second = root / "second"
            prepare_plateau_buildings(source, first, self.config())
            prepare_plateau_buildings(source, second, self.config())
            first_manifest = json.loads((first / MANIFEST_FILE).read_text("utf-8"))
            second_manifest = json.loads((second / MANIFEST_FILE).read_text("utf-8"))

        self.assertEqual(
            first_manifest["semantic_sha256"],
            second_manifest["semantic_sha256"],
        )
        self.assertEqual(first_manifest["counts"], second_manifest["counts"])

    def test_boundary_duplicate_is_removed_and_missing_height_is_preserved(self) -> None:
        flat_gml = GML.replace(" 16", " 4")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "citygml.zip"
            with zipfile.ZipFile(
                source, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for mesh in ("51352175", "51352176"):
                    archive.writestr(
                        f"udx/bldg/{mesh}_bldg_6697_op.gml", flat_gml
                    )
            config = PlateauPreparationConfig(
                center=GeoPoint(34.2325, 135.1917),
                radius_m=100,
                mesh_codes=("51352175", "51352176"),
            )
            output = prepare_plateau_buildings(source, root / "prepared", config)
            prepared = load_prepared_plateau_buildings(output)

        self.assertEqual(len(prepared.buildings), 1)
        self.assertTrue(prepared.buildings["height_m"].isna().iloc[0])
        self.assertEqual(prepared.manifest.counts["missing_height"], 1)

    def test_refuses_overwrite_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.create_source(root)
            output = root / "prepared"
            prepare_plateau_buildings(source, output, self.config())
            with self.assertRaises(FileExistsError):
                prepare_plateau_buildings(source, output, self.config())
            with (output / BUILDINGS_FILE).open("ab") as file:
                file.write(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_prepared_plateau_buildings(output)

    def test_rejects_missing_crs_and_invalid_xml(self) -> None:
        without_crs = GML.replace(
            ' srsName="http://www.opengis.net/def/crs/EPSG/0/6697"', ""
        )
        for content, message in (
            (without_crs, "CRS is missing"),
            ("<broken>", "invalid CityGML XML"),
        ):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with self.assertRaisesRegex(ValueError, message):
                    prepare_plateau_buildings(
                        self.create_source(root, content),
                        root / "prepared",
                        self.config(),
                    )


if __name__ == "__main__":
    unittest.main()
