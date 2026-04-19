from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _patch_pyvista_pytest_compat() -> None:
    try:
        from pyvista.core.pyvista_ndarray import pyvista_ndarray

        orig_eq = getattr(pyvista_ndarray, "__eq__", None)
        if callable(orig_eq) and not getattr(pyvista_ndarray, "_geoai_eq_patched", False):
            def _geoai_eq(self, other):
                result = orig_eq(self, other)
                if isinstance(result, bool):
                    return np.bool_(result)
                return result

            pyvista_ndarray.__eq__ = _geoai_eq
            pyvista_ndarray._geoai_eq_patched = True
    except Exception:
        pass

    try:
        from _pytest.python_api import ApproxBase

        orig_approx_eq = getattr(ApproxBase, "__eq__", None)
        if callable(orig_approx_eq) and not getattr(ApproxBase, "_geoai_eq_patched", False):
            def _geoai_pytest_eq(self, other):
                result = orig_approx_eq(self, other)
                if isinstance(result, bool):
                    return np.bool_(result)
                return result

            ApproxBase.__eq__ = _geoai_pytest_eq
            ApproxBase._geoai_eq_patched = True
    except Exception:
        pass


_patch_pyvista_pytest_compat()
