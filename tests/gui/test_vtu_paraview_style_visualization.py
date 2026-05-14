from pathlib import Path

from geoai_simkit.app.viewport.pyvista_adapter import PyVistaViewportAdapter
from geoai_simkit.geology.importers.meshio_importer import _read_meshio_fallback, _to_mesh_document


class _Plotter:
    def add_mesh(self, *args, **kwargs):
        return object()

    def remove_actor(self, *_args, **_kwargs):
        return None


def test_ascii_vtu_cell_scalar_is_preserved_for_categorical_soil_colors(tmp_path: Path) -> None:
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
    doc, meta = _to_mesh_document(mesh, block_id="imported", source_path=str(path))
    assert meta["active_cell_scalar"] == "SoilID"
    assert meta["preferred_geology_scalar"] == "SoilID"
    assert doc.cell_tags["SoilID"] == [101, 202]
    assert doc.cell_tags["geology_layer_id"] == ["101", "202"]


def test_viewport_prefers_paraview_like_layer_scalars_and_high_order_vtu_cells() -> None:
    class Mesh:
        cell_count = 3
        cell_tags = {"block_id": ["b", "b", "b"], "SoilID": [1, 2, 3], "vtkOriginalCellIds": [0, 1, 2]}
        metadata = {"active_cell_scalar": "SoilID"}

    adapter = PyVistaViewportAdapter(_Plotter())
    assert adapter._preferred_mesh_scalar(Mesh()) == "SoilID"
    assert adapter._vtk_cell_type("tet10", 10) == 24
    assert adapter._vtk_cell_type("hex20", 20) == 25
    assert adapter._vtk_cell_type("quad9", 9) == 28
