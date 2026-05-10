from __future__ import annotations

from abc import ABC, abstractmethod

import pyvista as pv


class GeometrySource(ABC):
    @abstractmethod
    def build(self) -> pv.DataSet | pv.MultiBlock:
        raise NotImplementedError
