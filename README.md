# geoai-simkit v10

`geoai-simkit` is a **graphics-first simulation platform starter** for geotechnical and related engineering problems. It is designed around four ideas:

- **geometry is editable/importable** (parametric scenes or IFC)
- **materials are pluggable** (linear elastic, Mohr–Coulomb, HSS/HSsmall-style)
- **solvers are replaceable** (current Warp-oriented backend with linear and nonlinear Hex8 paths)
- **post-processing is native** (in-app preview + ParaView/VTK/mesh export)

The package already contains:

- parametric pit example
- IFC import hooks
- voxelization for solver-friendly Hex8 grids
- stage-based analysis model
- Hex8 linear path
- Hex8 nonlinear path with material-state carry-over
- structural overlays (`truss2`, translational `beam2`, membrane-style `shellquad4`)
- node-pair interface contact/friction starter
- Qt/PyVista preview
- VTK / VTU / VTM / XDMF / OBJ / PLY / STL export
- ParaView stage bundle export (`.pvd` + per-stage `.vtu`)

It is still **not a full commercial-grade nonlinear FEM product**. The main remaining gaps are:

- fuller industrial shell quality / element stabilization beyond the current starter implementation
- mortar / surface-to-surface contact
- more rigorous Mohr–Coulomb corner/apex return mapping
- fuller HSsmall memory and cyclic rules
- more advanced sparse/global large-scale assembly beyond the current SciPy-backed starter path
- coupled seepage / effective stress / consolidation workflows


## What is new in v10

This revision focuses on **desktop usability and interaction design**:

- solver now runs in a **background Qt worker thread**, so the GUI no longer blocks during long solves
- added **stage/iteration progress bars** and live progress messages
- left control area is now a **workflow stepper** instead of a button stack
- added **region/material assignment editor** with direct binding to selected regions
- added **stage/boundary editor** for step-by-step setup
- added **validation panel**, **task table**, and **convergence history table**
- results page now separates **stage** and **field** selection
- root-directory launchers remain available (`run_demo.py`, `run_gui.py`, `run_checks.py`)

## What is new in v9

This revision focuses on **solver robustness and root-directory usability**:

- added a sparse-capable linear algebra helper with SciPy fallback
- nonlinear Hex8 path now supports backtracking line search and load cutbacks
- nonlinear convergence history is stored in `model.metadata["solver_history"]`
- root install now includes `scipy` and adds `requirements-solver.txt`
- environment checks now report SciPy availability

Earlier usability improvements remain in place:

- added root-level launchers:
  - `run_demo.py`
  - `run_gui.py`
  - `run_checks.py`
- added `python -m geoai_simkit ...` support through `__main__.py`
- added environment diagnostics via `geoai-simkit check-env`
- added split requirement files for base / UI / IFC / Warp / dev
- added a root `Makefile` for common tasks
- updated docs so you can run from the project root without first packaging/installing the wheel
- changed CLI imports to **lazy imports**, so `check-env` works even when GUI or solver extras are not installed

## How to run from the project root

Assuming you are in the repository root.

### Option A: run directly from root without installing the package

This is the fastest way to start.

```bash
python run_checks.py
python run_demo.py
python run_gui.py
```

These scripts automatically add `src/` to `PYTHONPATH`.

### Option B: use the module entrypoint from root

```bash
PYTHONPATH=src python -m geoai_simkit check-env
PYTHONPATH=src python -m geoai_simkit demo --out-dir exports_root
PYTHONPATH=src python -m geoai_simkit gui
```

### Option C: install editable and use the CLI

```bash
python -m pip install -e .
geoai-simkit check-env
geoai-simkit demo --out-dir exports_root
geoai-simkit gui
```

## Recommended dependency setup

### Minimal headless usage

```bash
python -m pip install -r requirements.txt
```

### Add GUI

```bash
python -m pip install -r requirements-ui.txt
```

### Add IFC import

```bash
python -m pip install -r requirements-ifc.txt
```

### Add Warp backend dependency

```bash
python -m pip install -r requirements-warp.txt
```

### Add test/dev tools

```bash
python -m pip install -r requirements-dev.txt
```

Or use the convenience targets:

```bash
make install
make install-ui
make install-ifc
make install-warp
make install-dev
make install-solver
```

## Typical root-directory workflow

```bash
python run_checks.py
python run_demo.py
```

This generates outputs under `exports_root/`.

Then open ParaView with the bundle, for example:

- `exports_root/pit_demo_bundle/pit_demo.pvd`

To launch the local viewer:

```bash
python run_gui.py
```

## In-app workflow

1. Create a parametric model or import IFC.
2. Check the left-side workflow stepper and validation list.
3. Voxelize / prepare a Hex8-friendly solver mesh if needed.
4. Select regions and assign materials in the material page.
5. Configure stages and boundary conditions in the stage page.
6. Run the solver in the background and track progress in the progress bars / task table.
7. Inspect stages and result fields in-app, then export to VTK/ParaView if needed.

## Current solver behavior

The current backend chooses among these paths:

- **nonlinear-hex8** if nonlinear materials, structures, or interfaces are present
- **linear-hex8** if the model is a Hex8-friendly volumetric mesh without nonlinear extras
- **graph-relaxation fallback** for arbitrary imported meshes not yet suitable for Hex8 solving

## Important notes for development

- `beam2` is currently a **translational engineering approximation**, not a full rotational beam element.
- `shellquad4` is currently **membrane-only**.
- contact is currently **node-pair penalty/friction**, not mortar contact.
- the Warp backend is still a **platform starter** and not yet a full Warp-native sparse FEM assembly stack.

## Handy commands

### Run checks

```bash
python run_checks.py
```

### Run the packaged demo

```bash
python run_demo.py
```

### Run tests

```bash
PYTHONPATH=src pytest -q
```

or

```bash
make test
```

### Launch the GUI

```bash
python run_gui.py
```

## Main modules

- `geoai_simkit.geometry.ifc_import` – IFC import via IfcOpenShell iterator
- `geoai_simkit.geometry.voxelize` – surface-to-volume voxelization helper
- `geoai_simkit.materials.registry` – pluggable material model registry
- `geoai_simkit.solver.warp_backend` – platform backend with linear/nonlinear Hex8 paths
- `geoai_simkit.solver.hex8_nonlinear` – nonlinear Hex8 path with state carry-over
- `geoai_simkit.solver.structural_elements` – structural overlays
- `geoai_simkit.solver.interface_elements` – contact/interface starter
- `geoai_simkit.post.exporters` – direct export + ParaView bundle export
- `geoai_simkit.app.main_window` – Qt + PyVista preview app


## v12 增强

- 统一右侧属性检查器（Selection / Actions / Solver）
- IFC 对象右键菜单：设为新 Region、归并到现有 Region、合并 Region、设置对象角色
- Geometry 页面新增对象/Region 编辑区
- Material 页面支持“当前参数 -> 选中区域”的自定义参数赋值
- Stage 页面支持录入初始增量、最大迭代、线搜索和备注
- 预览支持高亮选中对象/Region


## 额外网格划分依赖

```bash
python -m pip install -r requirements-meshing.txt
```

若本机安装了 `gmsh` 可执行程序，并安装了 `meshio`，即可在 GUI 的“网格划分流程”中选择 `gmsh_tet`。若不可用，软件会提示并可回退到体素化。
