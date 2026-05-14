# GeoAI SimKit v1.3.0-beta

GeoAI SimKit 1.3.0-beta is an engineering Beta build of the six-phase 3D geotechnical simulation workbench.

The default GUI launcher opens the phase-based workbench:

```text
地质 → 结构 → 网格 → 阶段配置 → 求解 → 结果查看
```

## One-click demo

The PySide six-phase workbench includes a `1.3 Demo` tab with three actions:

1. `一键加载 1.3 Demo`
2. `运行完整计算流程`
3. `导出 Demo 审查包`

The headless API is also available:

```bash
PYTHONPATH=src python - <<'PY'
from geoai_simkit.examples.release_1_3_0_workflow import run_release_1_3_0_workflow
result = run_release_1_3_0_workflow(output_dir='exports/release_1_3_0_demo_run')
print(result['ok'], result['acceptance']['status'])
print(result['artifacts']['project_path'])
PY
```

Expected status:

```text
accepted_1_3_0_beta
```

## GUI launch

```bash
python start_gui.py
python run_gui.py
python -m geoai_simkit gui
```

If `pyvista` and `pyvistaqt` are available, the launcher uses the NextGen 3D phase workbench. If they are unavailable but `PySide6` is available, it uses the modern PySide-only phase workbench. The old flat GUI is not the default; it is only available with:

```bash
GEOAI_SIMKIT_LEGACY_GUI=1 python start_gui.py
```

## Review bundle

The package contains an accepted 1.3.0 review bundle at:

```text
docs/release/release_1_3_0_review_bundle/
```

It includes the project file, validation report, compiler report, global Newton summary, demo pipeline report, VTK/JSON exports, engineering report and tutorial.

## Boundary

This is an engineering Beta workflow demonstration. It runs the complete built-in calculation flow, but it is not a certified commercial geotechnical solver. Native Gmsh/OCC, desktop GUI interaction and numerical benchmark tolerances should be verified on the target workstation before production sign-off.
