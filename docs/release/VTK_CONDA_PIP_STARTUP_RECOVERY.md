# VTK / PyVista startup recovery for conda environments

When GeoAI SimKit is launched from a conda environment, do not use
`pip --force-reinstall vtk` over a conda-installed VTK package. Conda packages do
not always include the pip `RECORD` metadata, so pip may fail with:

```text
Cannot uninstall vtk ... no RECORD file was found for vtk
```

This can leave the environment in a mixed state where `vtk` appears installed but
compiled VTK submodules such as `vtkmodules.vtkCommonMath` are not importable.

Recommended repair in conda:

```bash
conda activate ifc
conda install -c conda-forge vtk pyvista pyvistaqt pyside6 gmsh meshio
python start_gui.py
```

If the 3D VTK stack is still broken, the application can be launched in Qt-only
six-phase mode while the 3D environment is being repaired:

```bash
GEOAI_SIMKIT_DISABLE_PYVISTA=1 python start_gui.py
```

The six-phase workbench will still open. The 3D PyVista viewport will be disabled
until the VTK/PyVista stack is healthy.

For a clean pip-only setup, create a fresh virtual environment instead of mixing
pip and conda-managed VTK:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python start_gui.py
```
