# Startup dependency preflight VTK fix

This patch fixes a launcher failure where PyVista/VTK could be partially installed and the GUI crashed with:

```text
Failed to load vtkCommonDataModel: No module named vtkmodules.vtkCommonMath
```

## Changes

- `requirements.txt` now lists `vtk`, `pyvista` and `pyvistaqt` as explicit runtime dependencies instead of commented optional dependencies.
- `pyproject.toml` GUI extras now include `vtk>=9.2`.
- Startup preflight now validates required submodule imports, including:
  - `vtkmodules.vtkCommonCore`
  - `vtkmodules.vtkCommonMath`
  - `vtkmodules.vtkCommonDataModel`
- Broken or partial VTK/PyVista installs are reported as blocking dependency failures before the main GUI is launched.
- Recovery hints now include forced reinstall commands for `vtk`, `pyvista` and `pyvistaqt`.

## Recommended recovery command

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install --upgrade --force-reinstall numpy scipy vtk pyvista pyvistaqt
python -m pip install -r requirements.txt
```

For conda environments, prefer installing GUI/VTK packages from conda-forge when pip wheels are incompatible with the platform:

```bash
conda install -c conda-forge numpy scipy vtk pyvista pyvistaqt pyside6 gmsh meshio
```
