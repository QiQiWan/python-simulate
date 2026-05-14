# Strict startup dependency policy

GeoAI SimKit now performs a strict startup preflight. The main GUI is launched
only when the full required runtime stack is healthy:

- NumPy / SciPy / typing_extensions
- PySide6 / QtPy
- VTK with `vtkmodules.vtkCommonCore`, `vtkmodules.vtkCommonMath`, and `vtkmodules.vtkCommonDataModel`
- PyVista / pyvistaqt
- Gmsh / meshio

VTK/PyVista are no longer treated as optional for startup. This prevents opening
a partially functional GUI and failing later when the 3D viewport or meshing tools
are used.

## Conda environments

When VTK was installed by conda, do not run:

```bash
python -m pip install --force-reinstall vtk
```

Pip cannot uninstall a conda-managed VTK package because the package may not have
a pip `RECORD` file. Use conda-forge instead:

```bash
conda install -c conda-forge numpy scipy pyside6 vtk pyvista pyvistaqt gmsh meshio
python -m pip install -r requirements.txt
```

## Verify VTK before launching

```bash
python - <<'PY'
import vtk
import vtkmodules.vtkCommonCore
import vtkmodules.vtkCommonMath
import vtkmodules.vtkCommonDataModel
import pyvista
import pyvistaqt
print('vtk:', vtk.vtkVersion.GetVTKVersion())
print('pyvista:', pyvista.__version__)
print('pyvistaqt:', pyvistaqt.__version__)
print('VTK/PyVista stack OK')
PY
```
