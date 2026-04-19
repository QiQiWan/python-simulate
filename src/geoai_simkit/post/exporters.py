from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.post.stage_mesh import build_stage_dataset


SUPPORTED_EXPORTS = {
    ".vtu", ".vtk", ".vtm", ".xdmf", ".obj", ".ply", ".stl", ".vtp", ".vtkhdf"
}


class ExportManager:
    def export_model(self, model: SimulationModel, path: str | Path, binary: bool = True) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        ext = out.suffix.lower()
        if ext not in SUPPORTED_EXPORTS:
            raise ValueError(f"Unsupported export format: {ext}")
        data = model.mesh
        if isinstance(data, pv.MultiBlock):
            data.save(out)
            return out
        if ext in {".obj", ".ply", ".stl", ".vtp"}:
            surf = data.extract_surface(algorithm='dataset_surface')
            surf.save(out, binary=binary)
            return out
        data.save(out, binary=binary)
        return out

    def export_paraview_bundle(self, model: SimulationModel, directory: str | Path, stem: str | None = None) -> list[Path]:
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = stem or model.name
        produced: list[Path] = []
        if isinstance(model.mesh, pv.MultiBlock):
            path = out_dir / f"{stem}.vtm"
            model.mesh.save(path)
            produced.append(path)
        else:
            grid = model.mesh
            for ext in (".vtu", ".xdmf"):
                path = out_dir / f"{stem}{ext}"
                try:
                    grid.save(path)
                    produced.append(path)
                except Exception:
                    continue
        series = self.export_stage_series(model, out_dir, stem=stem)
        produced.extend(series)
        return produced

    def export_stage_series(
        self,
        model: SimulationModel,
        directory: str | Path,
        stem: str | None = None,
        displacement_scale: float = 1.0,
    ) -> list[Path]:
        out_dir = Path(directory)
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = stem or model.name
        produced: list[Path] = []
        stages = model.list_stages()
        if not stages:
            return produced

        pvd_root = ET.Element("VTKFile", type="Collection", version="0.1", byte_order="LittleEndian")
        collection = ET.SubElement(pvd_root, "Collection")

        for idx, stage in enumerate(stages):
            ds = build_stage_dataset(model, stage, displacement_scale=displacement_scale)
            stage_safe = stage.replace("/", "_").replace(" ", "_")
            filename = f"{stem}_{idx:03d}_{stage_safe}.vtu"
            path = out_dir / filename
            ds.save(path)
            produced.append(path)
            ET.SubElement(collection, "DataSet", timestep=str(idx), part="0", file=filename)

        pvd_path = out_dir / f"{stem}.pvd"
        ET.ElementTree(pvd_root).write(pvd_path, encoding="utf-8", xml_declaration=True)
        produced.append(pvd_path)
        return produced
