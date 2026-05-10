from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import math
import os
import time
from typing import Any, Callable

import numpy as np
import pyvista as pv

from geoai_simkit.core.model import SimulationModel
from geoai_simkit.core.types import RegionTag


@dataclass(slots=True)
class VoxelizeOptions:
    cell_size: float | None = None
    dims: tuple[int, int, int] | None = None
    padding: float = 0.0
    surface_only: bool = False
    worker_count: int = 0
    max_background_cells: int = 8_000_000


class VoxelizationError(RuntimeError):
    def __init__(
        self,
        object_name: str,
        reason: str,
        *,
        hint: str = "",
        details: str = "",
        stats: dict[str, Any] | None = None,
    ) -> None:
        self.object_name = object_name or "object"
        self.reason = reason
        self.hint = hint
        self.details = details
        self.stats = stats or {}
        parts = [f"{self.object_name}: {self.reason}"]
        if self.details:
            parts.append(self.details)
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        super().__init__(" | ".join(parts))


class VoxelMesher:
    """Convert IFC / scene surface geometry into a Hex8-friendly volumetric grid.

    This implementation keeps region tags by voxelizing each object independently and
    returning a ``MultiBlock`` when more than one object produces volume cells.
    """

    def __init__(
        self,
        options: VoxelizeOptions | None = None,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        log_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.options = options or VoxelizeOptions()
        self.progress_callback = progress_callback
        self.log_callback = log_callback

    def voxelize_model(self, model: SimulationModel) -> SimulationModel:
        data = model.mesh
        out = pv.MultiBlock()
        region_tags: list[RegionTag] = []
        cell_offset = 0
        started_at = time.perf_counter()

        if isinstance(data, pv.MultiBlock):
            items = [(str(key), data[key]) for key in data.keys()]
        else:
            items = [(model.name, data)]
        items = [(k, b) for k, b in items if b is not None and int(getattr(b, "n_cells", 0) or 0) > 0]
        total = len(items)
        if total == 0:
            raise RuntimeError("Voxelization aborted: no mesh blocks with cells were found.")

        workers = self._resolve_worker_count(total)
        self._emit(
            phase="voxelize-start",
            value=12,
            message=f"Voxelization queued for {total} object(s) with {workers} worker(s).",
            object_count=total,
            worker_count=workers,
            log=True,
        )

        warnings: list[str] = []
        failures: list[VoxelizationError] = []
        ordered_results: dict[int, dict[str, Any]] = {}

        if workers <= 1 or total <= 1:
            for index, (key, block) in enumerate(items, start=1):
                result = self._voxelize_item(index, total, key, block)
                ordered_results[index - 1] = result
                self._emit_object_result(result)
        else:
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="voxelize") as pool:
                future_map = {
                    pool.submit(self._voxelize_item, index, total, key, block): index - 1
                    for index, (key, block) in enumerate(items, start=1)
                }
                for future in as_completed(future_map):
                    idx = future_map[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # pragma: no cover - defensive fallback
                        key = items[idx][0]
                        result = {
                            "ok": False,
                            "object_index": idx + 1,
                            "object_count": total,
                            "object_name": key,
                            "region_name": key.split("/")[-1] or "region",
                            "error": VoxelizationError(
                                key,
                                "Worker crashed while voxelizing the object.",
                                details=str(exc),
                                hint="Retry with worker_count=1 to isolate thread-safety issues.",
                            ),
                        }
                    ordered_results[idx] = result
                    self._emit_object_result(result)

        success_count = 0
        for idx in range(total):
            result = ordered_results[idx]
            if not result.get("ok"):
                failures.append(result["error"])
                continue
            success_count += 1
            vox = result["grid"]
            region_name = result["region_name"]
            out[region_name] = vox
            region_tags.append(
                RegionTag(
                    name=region_name,
                    cell_ids=np.arange(cell_offset, cell_offset + vox.n_cells, dtype=np.int64),
                    metadata={
                        "source": result["object_name"],
                        "voxelized": True,
                        "dims": tuple(int(v) for v in result["stats"].get("dims", (0, 0, 0))),
                        "spacing": tuple(float(v) for v in result["stats"].get("spacing", (0.0, 0.0, 0.0))),
                    },
                )
            )
            cell_offset += vox.n_cells
            warning_text = str(result["stats"].get("warning") or "").strip()
            if warning_text:
                warnings.append(f"{result['object_name']}: {warning_text}")

        elapsed = time.perf_counter() - started_at
        if success_count == 0:
            summary = "; ".join(str(err) for err in failures[:4])
            if len(failures) > 4:
                summary += f"; ... and {len(failures) - 4} more failure(s)"
            raise RuntimeError(f"Voxelization failed for all {total} object(s). {summary}")

        model.mesh = out if len(out.keys()) > 1 else next((out[k] for k in out.keys()), model.mesh)
        model.region_tags = region_tags
        model.metadata["voxelized"] = True
        model.metadata["meshed_by"] = "voxel_hex8"
        model.metadata["voxelize_options"] = {
            "cell_size": self.options.cell_size,
            "dims": self.options.dims,
            "padding": self.options.padding,
            "surface_only": self.options.surface_only,
            "worker_count": workers,
            "max_background_cells": int(self.options.max_background_cells),
        }
        model.metadata["mesh_summary"] = {
            "method": "voxel_hex8",
            "object_count": total,
            "objects_succeeded": success_count,
            "objects_failed": len(failures),
            "warning_count": len(warnings),
            "elapsed_seconds": elapsed,
            "regions": len(region_tags),
            "cells": int(sum(int(getattr(out[k], "n_cells", 0) or 0) for k in out.keys())),
            "points": int(sum(int(getattr(out[k], "n_points", 0) or 0) for k in out.keys())),
            "worker_count": workers,
        }
        if warnings:
            model.metadata.setdefault("mesh_warnings", []).extend(warnings)
        if failures:
            model.metadata.setdefault("mesh_failures", []).extend(str(err) for err in failures)

        self._emit(
            phase="voxelize-finished",
            value=88,
            message=(
                f"Voxelization finished: {success_count}/{total} object(s), "
                f"{model.metadata['mesh_summary']['cells']} cells, {model.metadata['mesh_summary']['regions']} region(s), "
                f"elapsed {elapsed:.2f}s."
            ),
            object_count=total,
            object_success=success_count,
            object_failed=len(failures),
            summary=model.metadata["mesh_summary"],
            log=True,
        )
        return model

    def _resolve_worker_count(self, object_count: int) -> int:
        requested = int(getattr(self.options, "worker_count", 0) or 0)
        if requested > 0:
            return max(1, min(requested, object_count))
        cpu_count = max(1, int(os.cpu_count() or 1))
        return max(1, min(object_count, max(1, cpu_count - 1), 8))

    def _infer_region_name(self, key: str, block: pv.DataSet) -> str:
        if "region_name" in block.field_data and len(block.field_data["region_name"]):
            return str(block.field_data["region_name"][0])
        leaf = key.split("/")[-1]
        return leaf or "region"

    def _voxelize_item(self, object_index: int, object_count: int, key: str, block: pv.DataSet) -> dict[str, Any]:
        region_name = self._infer_region_name(key, block)
        started_at = time.perf_counter()
        stats = {
            "source_cells": int(getattr(block, "n_cells", 0) or 0),
            "source_points": int(getattr(block, "n_points", 0) or 0),
            "elapsed_seconds": 0.0,
        }
        try:
            grid, info = self._voxelize_block(block, object_name=key)
            stats.update(info)
            stats["elapsed_seconds"] = time.perf_counter() - started_at
            grid.cell_data["region_name"] = np.array([region_name] * grid.n_cells)
            grid.field_data["region_name"] = np.array([region_name])
            return {
                "ok": True,
                "object_index": object_index,
                "object_count": object_count,
                "object_name": key,
                "region_name": region_name,
                "grid": grid,
                "stats": stats,
            }
        except VoxelizationError as exc:
            stats["elapsed_seconds"] = time.perf_counter() - started_at
            exc.stats.update({k: v for k, v in stats.items() if k not in exc.stats})
            return {
                "ok": False,
                "object_index": object_index,
                "object_count": object_count,
                "object_name": key,
                "region_name": region_name,
                "error": exc,
                "stats": stats,
            }
        except Exception as exc:  # pragma: no cover - unexpected but better diagnostics
            stats["elapsed_seconds"] = time.perf_counter() - started_at
            return {
                "ok": False,
                "object_index": object_index,
                "object_count": object_count,
                "object_name": key,
                "region_name": region_name,
                "error": VoxelizationError(
                    key,
                    "Unexpected exception during voxelization.",
                    details=str(exc),
                    hint="Inspect the object geometry and traceback; retry with a larger cell size if the mesh is extremely dense.",
                    stats=stats,
                ),
                "stats": stats,
            }

    def _emit_object_result(self, result: dict[str, Any]) -> None:
        idx = int(result.get("object_index", 0) or 0)
        total = max(1, int(result.get("object_count", 1) or 1))
        value = 15 + int(70.0 * idx / total)
        if result.get("ok"):
            stats = result.get("stats", {})
            dims = tuple(int(v) for v in stats.get("dims", (0, 0, 0)))
            message = (
                f"Voxelized {result['object_name']} ({idx}/{total}) -> {int(stats.get('result_cells', 0))} cells, "
                f"dims={dims}, spacing={tuple(round(float(v), 4) for v in stats.get('spacing', (0.0, 0.0, 0.0)))}, "
                f"elapsed {float(stats.get('elapsed_seconds', 0.0)):.2f}s"
            )
            self._emit(
                phase="object-complete",
                value=value,
                message=message,
                object_name=result["object_name"],
                object_index=idx,
                object_count=total,
                stats=stats,
                log=True,
            )
            warning_text = str(stats.get("warning") or "").strip()
            if warning_text:
                self._emit(
                    phase="object-warning",
                    value=value,
                    message=f"{result['object_name']}: {warning_text}",
                    object_name=result["object_name"],
                    object_index=idx,
                    object_count=total,
                    severity="warning",
                    stats=stats,
                    log=True,
                )
            return
        err = result["error"]
        self._emit(
            phase="object-failed",
            value=value,
            message=str(err),
            object_name=result["object_name"],
            object_index=idx,
            object_count=total,
            severity="error",
            hint=getattr(err, "hint", ""),
            stats=getattr(err, "stats", {}),
            log=True,
        )

    def _voxelize_block(self, block: pv.DataSet, *, object_name: str) -> tuple[pv.UnstructuredGrid, dict[str, Any]]:
        if (
            not self.options.surface_only
            and isinstance(block, pv.UnstructuredGrid)
            and int(getattr(block, "n_cells", 0) or 0) > 0
            and hasattr(block, "celltypes")
        ):
            try:
                celltypes = np.asarray(block.celltypes, dtype=np.int64)
            except Exception:
                celltypes = np.empty((0,), dtype=np.int64)
            hex_types = {int(pv.CellType.HEXAHEDRON), int(pv.CellType.VOXEL)}
            if celltypes.size and np.all(np.isin(celltypes, list(hex_types))):
                bounds = np.asarray(block.bounds, dtype=float)
                spacing = self._spacing(bounds)
                kept = block.cast_to_unstructured_grid()
                return kept, {
                    "bounds": bounds.tolist(),
                    "spacing": spacing,
                    "dims": (0, 0, 0),
                    "estimated_cells": int(kept.n_cells),
                    "selected_cells": int(kept.n_cells),
                    "result_cells": int(kept.n_cells),
                    "warning": "Input was already a Hex/Voxel volume mesh, so surface voxelization was skipped.",
                }
        surf = block.extract_surface(algorithm='dataset_surface').triangulate()
        if int(getattr(surf, "n_points", 0) or 0) < 3 or int(getattr(surf, "n_cells", 0) or 0) == 0:
            raise VoxelizationError(
                object_name,
                "Surface extraction returned no usable faces.",
                hint="Check whether the IFC/object geometry is empty, hidden, or only contains line/point primitives.",
            )
        bounds = np.asarray(surf.bounds, dtype=float)
        if not np.all(np.isfinite(bounds)):
            raise VoxelizationError(
                object_name,
                "Object bounds are invalid (NaN/Inf).",
                hint="Repair the source geometry or rebuild the object before voxelization.",
                stats={"bounds": bounds.tolist()},
            )
        extents = np.array([
            max(bounds[1] - bounds[0], 0.0),
            max(bounds[3] - bounds[2], 0.0),
            max(bounds[5] - bounds[4], 0.0),
        ])
        if np.any(extents <= 1.0e-9):
            raise VoxelizationError(
                object_name,
                "Object thickness is effectively zero on at least one axis.",
                hint="Use a solid/closed body, or increase padding/cell size for thin plates and shells.",
                stats={"bounds": bounds.tolist(), "extents": extents.tolist()},
            )
        if self.options.padding:
            bounds[[0, 2, 4]] -= self.options.padding
            bounds[[1, 3, 5]] += self.options.padding
        dx, dy, dz = self._spacing(bounds)
        dims = (
            max(2, int(math.ceil((bounds[1] - bounds[0]) / dx)) + 1),
            max(2, int(math.ceil((bounds[3] - bounds[2]) / dy)) + 1),
            max(2, int(math.ceil((bounds[5] - bounds[4]) / dz)) + 1),
        )
        estimated_cells = max(1, (dims[0] - 1) * (dims[1] - 1) * (dims[2] - 1))
        if estimated_cells > int(self.options.max_background_cells):
            raise VoxelizationError(
                object_name,
                "Background voxel grid would be too large for the current cell size.",
                details=(
                    f"Requested dims={dims} -> about {estimated_cells:,} candidate cells with spacing "
                    f"({dx:.4g}, {dy:.4g}, {dz:.4g})."
                ),
                hint="Increase cell size, reduce padding, or voxelize this object separately.",
                stats={"dims": dims, "spacing": (dx, dy, dz), "estimated_cells": estimated_cells},
            )
        img = pv.ImageData(
            dimensions=dims,
            spacing=(dx, dy, dz),
            origin=(bounds[0], bounds[2], bounds[4]),
        )
        if self.options.surface_only:
            shell = img.extract_surface().triangulate().cast_to_unstructured_grid()
            return shell, {
                "bounds": bounds.tolist(),
                "spacing": (dx, dy, dz),
                "dims": dims,
                "estimated_cells": estimated_cells,
                "selected_cells": int(shell.n_cells),
                "result_cells": int(shell.n_cells),
            }

        centers = img.cell_centers()
        warning = ""
        try:
            if hasattr(centers, 'select_interior_points'):
                try:
                    selected = centers.select_interior_points(surf, tolerance=0.0, check_surface=False)
                except TypeError:
                    selected = centers.select_interior_points(surf)
            else:
                selected = centers.select_enclosed_points(surf, tolerance=0.0, check_surface=False)
            raw_mask = np.asarray(selected.point_data.get("SelectedPoints", []), dtype=np.uint8)
            mask = raw_mask.astype(bool)
        except Exception as exc:
            warning = (
                "select_enclosed_points failed; bbox fallback was used. "
                "This usually means the surface is open/non-manifold or too complex for a watertight test."
            )
            mask = np.ones(img.n_cells, dtype=bool)
            selected = None
            selected_error = str(exc)
        else:
            selected_error = ""

        selected_count = int(np.count_nonzero(mask))
        if selected_count == 0:
            raise VoxelizationError(
                object_name,
                "No interior cells were selected by the enclosure test.",
                details=(
                    f"dims={dims}, spacing=({dx:.4g}, {dy:.4g}, {dz:.4g}), source surface cells={int(surf.n_cells)}"
                ),
                hint="The object is likely not closed/watertight, or the cell size is too coarse/fine for the enclosed volume.",
                stats={"dims": dims, "spacing": (dx, dy, dz), "estimated_cells": estimated_cells},
            )
        kept = img.extract_cells(np.where(mask)[0]).cast_to_unstructured_grid()
        if int(getattr(kept, "n_cells", 0) or 0) == 0:
            raise VoxelizationError(
                object_name,
                "Voxel extraction produced an empty volume grid.",
                hint="Check for self-intersections/open shells; if needed increase padding or cell size.",
                stats={"dims": dims, "spacing": (dx, dy, dz), "selected_cells": selected_count},
            )
        info = {
            "bounds": bounds.tolist(),
            "spacing": (dx, dy, dz),
            "dims": dims,
            "estimated_cells": estimated_cells,
            "selected_cells": selected_count,
            "result_cells": int(kept.n_cells),
            "warning": warning,
        }
        if selected is not None:
            info["selection_ratio"] = float(selected_count) / max(1, estimated_cells)
        if selected_error:
            info["selection_error"] = selected_error
        return kept, info

    def _spacing(self, bounds: np.ndarray) -> tuple[float, float, float]:
        if self.options.dims is not None:
            nx, ny, nz = self.options.dims
            dx = max((bounds[1] - bounds[0]) / max(nx, 1), 1e-6)
            dy = max((bounds[3] - bounds[2]) / max(ny, 1), 1e-6)
            dz = max((bounds[5] - bounds[4]) / max(nz, 1), 1e-6)
            return dx, dy, dz
        if self.options.cell_size is not None:
            h = max(float(self.options.cell_size), 1e-6)
            return h, h, h
        ext = np.array([
            max(bounds[1] - bounds[0], 1e-6),
            max(bounds[3] - bounds[2], 1e-6),
            max(bounds[5] - bounds[4], 1e-6),
        ])
        h = float(np.max(ext) / 24.0)
        return h, h, h

    def _emit(self, **payload: Any) -> None:
        if self.progress_callback is not None:
            try:
                self.progress_callback(payload)
            except Exception:
                pass
        text = str(payload.get("message") or "").strip()
        if text and (payload.get("log") or payload.get("phase") in {"object-failed", "object-warning"}) and self.log_callback is not None:
            try:
                self.log_callback(text)
            except Exception:
                pass
