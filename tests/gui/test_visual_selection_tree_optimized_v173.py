from geoai_simkit.app.panels.object_tree import build_compact_engineering_object_tree
from geoai_simkit.app.viewport.viewport_state import ViewportState
from geoai_simkit.geology.importers.meshio_importer import _read_meshio_fallback, _to_mesh_document
from geoai_simkit.geoproject.document import GeoProjectDocument, GeometryVolume, SoilCluster


def _project_with_imported_mesh(tmp_path):
    path = tmp_path / "layers.vtu"
    path.write_text(
        """<?xml version=\"1.0\"?>
<VTKFile type=\"UnstructuredGrid\" version=\"0.1\" byte_order=\"LittleEndian\">
<UnstructuredGrid><Piece NumberOfPoints=\"8\" NumberOfCells=\"2\">
<Points><DataArray type=\"Float64\" NumberOfComponents=\"3\" format=\"ascii\">
0 0 0  1 0 0  0 1 0  0 0 1  1 0 1  1 1 1  0 1 1  1 1 0
</DataArray></Points>
<Cells>
<DataArray type=\"Int32\" Name=\"connectivity\" format=\"ascii\">0 1 2 3  4 5 6 7</DataArray>
<DataArray type=\"Int32\" Name=\"offsets\" format=\"ascii\">4 8</DataArray>
<DataArray type=\"UInt8\" Name=\"types\" format=\"ascii\">10 10</DataArray>
</Cells>
<CellData Scalars=\"SoilID\"><DataArray type=\"Int32\" Name=\"SoilID\" format=\"ascii\">101 202</DataArray></CellData>
</Piece></UnstructuredGrid></VTKFile>
""",
        encoding="utf-8",
    )
    mesh = _read_meshio_fallback(path)
    doc, _ = _to_mesh_document(mesh, block_id="imported", source_path=str(path))
    doc.metadata["display_name"] = "导入地质体"
    doc.metadata["layer_properties"] = {"101": {"name": "粉质黏土", "material_id": "clay"}}
    project = GeoProjectDocument.create_empty(name="demo")
    project.mesh_model.attach_mesh(doc)
    project.geometry_model.volumes["imported"] = GeometryVolume(
        id="imported",
        name="imported",
        bounds=(0, 1, 0, 1, 0, 1),
        role="soil",
        material_id="soil_default",
        metadata={"source": "meshio_geology_importer"},
    )
    project.soil_model.add_cluster(SoilCluster(
        id="cluster_imported",
        name="Cluster imported",
        volume_ids=["imported"],
        material_id="soil_default",
        metadata={"source": "meshio_geology_importer"},
    ))
    return project


def test_compact_tree_shows_only_engineering_groups_and_layer_props(tmp_path):
    project = _project_with_imported_mesh(tmp_path)
    root = build_compact_engineering_object_tree(project)
    assert [child.label.split(" (")[0] for child in root.children] == ["地质体", "围护墙", "水平支撑", "梁", "锚杆"]
    geology_group = root.children[0]
    assert len(geology_group.children) == 1
    imported = geology_group.children[0]
    assert imported.entity_id == "imported_geology_model"
    assert any(child.entity_id == "geology_layer:101" and "粉质黏土" in child.label and child.metadata["material_id"] == "clay" for child in imported.children)


def test_imported_mesh_placeholder_volume_renders_outline_only(tmp_path):
    project = _project_with_imported_mesh(tmp_path)
    state = ViewportState()
    state.update_from_geoproject_document(project)
    primitive = state.primitives["primitive:block:imported"]
    assert primitive.metadata["render_mode"] == "outline_only"
    assert primitive.metadata["source"] == "meshio_geology_importer"
