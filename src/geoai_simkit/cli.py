from __future__ import annotations

import argparse
from pathlib import Path
import sys

from geoai_simkit._version import __version__


def _cmd_check(args: argparse.Namespace) -> int:
    from geoai_simkit.env_check import collect_environment_checks, format_environment_report

    print(format_environment_report(collect_environment_checks()))
    return 0


def _cmd_gui(args: argparse.Namespace) -> int:
    # All install-time GUI launches share the same canonical launcher as
    # repository-root start_gui.py.  This prevents console scripts from entering
    # historical Qt windows that do not contain the repaired import/assembly
    # action dispatcher.
    from geoai_simkit.app.launcher_entry import main as launcher_main

    argv = []
    if bool(getattr(args, "debug", False)):
        argv.append("--debug")
    log_dir = getattr(args, "log_dir", None)
    if log_dir:
        argv.extend(["--log-dir", str(log_dir)])
    if bool(getattr(args, "qt_only", False)):
        argv.append("--qt-only")
    return int(launcher_main(argv, launcher_name="geoai-simkit gui"))


def _cmd_demo(args: argparse.Namespace) -> int:
    from geoai_simkit.examples.pit_example import build_demo_case
    from geoai_simkit.pipeline.runner import AnalysisExportSpec, AnalysisTaskSpec, GeneralFEMSolver

    out_dir = Path(args.out_dir)
    case = build_demo_case(smoke=not bool(args.full))
    task = AnalysisTaskSpec(
        case=case,
        execution_profile=str(args.profile),
        device=args.device,
        export=AnalysisExportSpec(out_dir=out_dir, stem='pit_demo', export_runtime_bundle=False),
    )
    result = GeneralFEMSolver().run_task(task)
    print(f'case={case.name}')
    print(f'backend={result.solved_model.metadata.get("last_solver_backend", "runtime")}')
    print(f'stages={", ".join(result.solved_model.metadata.get("stages_run", []))}')
    if result.metadata.get('exports'):
        print(f'exports={result.metadata["exports"]}')
    else:
        print(f'out_dir={out_dir}')
    return 0


def _cmd_export_case(args: argparse.Namespace) -> int:
    from geoai_simkit.examples.foundation_pit_showcase import build_foundation_pit_showcase_case
    from geoai_simkit.pipeline.io import save_case_spec

    path = Path(args.path)
    save_case_spec(build_foundation_pit_showcase_case(), path)
    print(f'wrote {path}')
    return 0


def _cmd_tet4_smoke(args: argparse.Namespace) -> int:
    from geoai_simkit.examples.tet4_stage_smoke import run_tiny_tet4_stage_smoke

    summary = run_tiny_tet4_stage_smoke(args.out)
    print(f"case={summary['case_name']}")
    print(f"backend={summary['backend']}")
    for row in summary.get('stages', []):
        print(
            f"stage={row['stage']} status={row['status']} "
            f"active_cells={row['active_cell_count']} "
            f"max_u={row['max_displacement']:.6e} "
            f"max_vm={row['max_von_mises']:.6e} "
            f"contact_eff={dict(row.get('contact_assembly', {}) or {}).get('effective_pair_count', 0)} "
            f"contact_inactive={dict(row.get('contact_assembly', {}) or {}).get('inactive_region_pair_count', 0)} "
            f"contact_missing_geom={dict(row.get('contact_assembly', {}) or {}).get('missing_geometry_pair_count', 0)}"
        )
    if summary.get('result_package'):
        pkg = summary['result_package']
        print(f"result_package={pkg.get('manifest_path', pkg.get('package_dir', ''))}")
    if summary.get('out_path'):
        print(f"summary={summary['out_path']}")
    return 0


def _cmd_pit_tet4_smoke(args: argparse.Namespace) -> int:
    from geoai_simkit.examples.pit_tet4_stage_smoke import run_foundation_pit_tet4_stage_smoke

    summary = run_foundation_pit_tet4_stage_smoke(args.out, result_dir=args.result_dir)
    print(f"case={summary['case_name']}")
    print(f"backend={summary['backend']}")
    grid = summary.get('grid', {})
    print(f"grid=points:{grid.get('point_count', 0)} cells:{grid.get('cell_count', 0)} regions:{grid.get('region_count', 0)}")
    contact = summary.get('contact_summary', {})
    print(f"contacts={contact.get('pair_count', 0)} policies={contact.get('by_mesh_policy', {})}")
    for row in summary.get('stages', []):
        print(
            f"stage={row['stage']} status={row['status']} "
            f"active_cells={row['active_cell_count']} "
            f"max_u={row['max_displacement']:.6e} "
            f"max_vm={row['max_von_mises']:.6e} "
            f"contact_eff={dict(row.get('contact_assembly', {}) or {}).get('effective_pair_count', 0)} "
            f"contact_inactive={dict(row.get('contact_assembly', {}) or {}).get('inactive_region_pair_count', 0)} "
            f"contact_missing_geom={dict(row.get('contact_assembly', {}) or {}).get('missing_geometry_pair_count', 0)} "
            f"release_loads={dict(row.get('release_loads', {}) or {}).get('load_count', 0)} "
            f"init_rhs={dict(row.get('initial_stress', {}) or {}).get('rhs_contribution_norm', 0.0)} "
            f"nl_iter={dict(row.get('nonlinear', {}) or {}).get('iteration_count', 0)} "
            f"yielded={dict(row.get('nonlinear', {}) or {}).get('yielded_cell_count', 0)} "
            f"inc_u={float(row.get('max_increment_displacement', 0.0) or 0.0):.6e} "
            f"res_ratio={dict(row.get('energy', {}) or {}).get('residual_to_rhs_ratio', 0.0)}"
        )
    if summary.get('result_package'):
        pkg = summary['result_package']
        print(f"result_package={pkg.get('manifest_path', pkg.get('package_dir', ''))}")
    if summary.get('out_path'):
        print(f"summary={summary['out_path']}")
    return 0




def _cmd_result_package_info(args: argparse.Namespace) -> int:
    from geoai_simkit.results import build_stage_package_gui_payload

    payload = build_stage_package_gui_payload(args.path)
    print(f"case={payload.get('case_name', '')}")
    print(f"format={payload.get('format', '')}")
    print(f"stages={payload.get('stage_count', 0)} fields={payload.get('field_count', 0)}")
    contact = dict(payload.get('contact_panel', {}) or {})
    diag = dict(contact.get('diagnostic_counts', {}) or {})
    if contact.get('available'):
        print(
            "contact="
            f"effective:{diag.get('effective_pair_count_sum', 0)} "
            f"inactive:{diag.get('inactive_region_pair_count_sum', 0)} "
            f"missing_geometry:{diag.get('missing_geometry_pair_count_sum', 0)}"
        )
    release = dict(payload.get('release_panel', {}) or {})
    rdiag = dict(release.get('diagnostic_counts', {}) or {})
    if release.get('available'):
        print(
            "release="
            f"released:{rdiag.get('released_count_sum', 0)} "
            f"closed:{rdiag.get('closed_count_sum', 0)} "
            f"unknown:{rdiag.get('unknown_count_sum', 0)}"
        )
    release_load = dict(payload.get('release_load_panel', {}) or {})
    if release_load.get('available'):
        print(
            "release_load="
            f"loads:{dict(release_load.get('diagnostic_counts', {}) or {}).get('applied_load_count_sum', 0)} "
            f"force_norm:{release_load.get('total_force_norm', 0.0)}"
        )
    geostatic = dict(payload.get('geostatic_panel', {}) or {})
    if geostatic.get('available'):
        stats = dict(geostatic.get('stats', {}) or {})
        print(
            "geostatic="
            f"sigma_v_max:{stats.get('sigma_v_max', 0.0)} "
            f"stress_l2_sum:{stats.get('stress_l2_norm_sum', 0.0)}"
        )
    initial_stress = dict(payload.get('initial_stress_panel', {}) or {})
    if initial_stress.get('available'):
        idiag = dict(initial_stress.get('diagnostic_counts', {}) or {})
        print(
            "initial_stress="
            f"enabled_stages:{idiag.get('enabled_stage_count', 0)} "
            f"rhs_norm_sum:{idiag.get('rhs_contribution_norm_sum', 0.0)}"
        )
    nonlinear = dict(payload.get('nonlinear_panel', {}) or {})
    if nonlinear.get('available'):
        ndiag = dict(nonlinear.get('diagnostic_counts', {}) or {})
        print(
            "nonlinear="
            f"enabled_stages:{ndiag.get('enabled_stage_count', 0)} "
            f"converged_stages:{ndiag.get('converged_stage_count', 0)} "
            f"yielded_cells:{ndiag.get('yielded_cell_count_sum', 0)} "
            f"max_iter:{ndiag.get('max_iteration_count', 0)}"
        )
    nonlinear_material_residual = dict(payload.get('nonlinear_material_residual_panel', {}) or {})
    if nonlinear_material_residual.get('available'):
        rdiag = dict(nonlinear_material_residual.get('diagnostic_counts', {}) or {})
        print(
            "nonlinear_material_residual="
            f"max_ratio:{rdiag.get('max_residual_to_external_rhs_ratio', 0.0)} "
            f"max_norm:{rdiag.get('max_residual_free_norm', 0.0)}"
        )
    material_state = dict(payload.get('material_state_panel', {}) or {})
    if material_state.get('available'):
        mdiag = dict(material_state.get('diagnostic_counts', {}) or {})
        print(
            "material_state="
            f"cells:{mdiag.get('cell_state_count', 0)} "
            f"yielded:{mdiag.get('yielded_cell_count', 0)} "
            f"yield_ratio:{mdiag.get('yielded_ratio', 0.0)}"
        )
    solver_acceptance = dict(payload.get('solver_acceptance_panel', {}) or {})
    if solver_acceptance.get('available'):
        adiag = dict(solver_acceptance.get('diagnostic_counts', {}) or {})
        print(
            "solver_acceptance="
            f"accepted:{adiag.get('accepted_stage_count', 0)} "
            f"warnings:{adiag.get('warning_stage_count', 0)} "
            f"failed:{adiag.get('failed_stage_count', 0)} "
            f"all_accepted:{solver_acceptance.get('all_accepted', False)}"
        )
    solver_balance = dict(payload.get('solver_balance_panel', {}) or {})
    if solver_balance.get('available'):
        sdiag = dict(solver_balance.get('diagnostic_counts', {}) or {})
        print(
            "solver_balance="
            f"max_residual_ratio:{sdiag.get('max_residual_to_rhs_ratio', 0.0)} "
            f"max_energy_error:{sdiag.get('max_relative_energy_balance_error', 0.0)}"
        )
    preview = dict(payload.get('preview_panel', {}) or {})
    if preview.get('available'):
        print(f"preview=default_stage:{preview.get('default_stage', '')} default_field:{preview.get('default_field', '')} entries:{preview.get('entry_count', 0)}")
    for issue in list(contact.get('issues', []) or []) + list(release.get('issues', []) or []) + list(release_load.get('issues', []) or []) + list(initial_stress.get('issues', []) or []) + list(nonlinear.get('issues', []) or []) + list(nonlinear_material_residual.get('issues', []) or []) + list(solver_acceptance.get('issues', []) or []):
        print(f"issue={issue.get('severity', '')}:{issue.get('id', '')} count={issue.get('count', '')}")
    print(f"manifest={payload.get('manifest_path', '')}")
    return 0


def _cmd_result_preview(args: argparse.Namespace) -> int:
    from geoai_simkit.results import build_result_field_preview, export_result_field_preview_csv

    preview = build_result_field_preview(args.path, stage=args.stage, field=args.field, max_rows=int(args.rows))
    if not preview.get('available'):
        print(f"preview_error={preview.get('error', 'unknown')}", file=sys.stderr)
        return 2
    print(f"case={preview.get('case_name', '')}")
    print(f"stage={preview.get('stage', '')} field={preview.get('field', '')} association={preview.get('association', '')}")
    print(f"shape={preview.get('shape', [])} dtype={preview.get('dtype', '')} rows_shown={preview.get('shown_row_count', 0)}")
    stats = dict(preview.get('stats', {}) or {})
    print(f"stats=min:{stats.get('min')} max:{stats.get('max')} mean:{stats.get('mean')} l2:{stats.get('l2_norm')}")
    for row in list(preview.get('preview_rows', []) or []):
        print(f"row[{row.get('index')}]={row.get('values')}")
    if args.csv:
        exported = export_result_field_preview_csv(args.path, args.csv, stage=args.stage, field=args.field, max_rows=int(args.csv_rows))
        print(f"csv={exported['path']} rows={exported['rows_written']}")
    return 0
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='geoai-simkit', description='GeoAI finite-element simulation workbench utilities')
    parser.add_argument('--version', action='version', version=f'geoai-simkit {__version__}')
    sub = parser.add_subparsers(dest='command')

    p_check = sub.add_parser('check', help='Check runtime, GUI, meshing, and GPU dependencies')
    p_check.set_defaults(func=_cmd_check)

    p_gui = sub.add_parser('gui', help='Launch the desktop workbench')
    p_gui.add_argument('--debug', action='store_true', help='Enable geometry-kernel debug logging for this GUI run')
    p_gui.add_argument('--log-dir', default=None, help='Debug log directory; defaults to ./log when --debug is used')
    p_gui.add_argument('--qt-only', action='store_true', help='Disable the PyVista/VTK viewport adapter')
    p_gui.set_defaults(func=_cmd_gui)

    p_demo = sub.add_parser('demo', help='Run the built-in foundation pit smoke demo')
    p_demo.add_argument('--out-dir', default='exports/demo', help='Output directory')
    p_demo.add_argument('--profile', default='cpu-robust', choices=['auto', 'cpu-robust', 'cpu-debug', 'gpu'])
    p_demo.add_argument('--device', default=None)
    p_demo.add_argument('--full', action='store_true', help='Use the larger nonlinear demo case')
    p_demo.set_defaults(func=_cmd_demo)

    p_export = sub.add_parser('export-case', help='Write the built-in showcase case JSON')
    p_export.add_argument('path', nargs='?', default='foundation_pit_showcase.geoai.json')
    p_export.set_defaults(func=_cmd_export_case)

    p_tet4 = sub.add_parser('tet4-smoke', help='Run a dependency-light Tet4 stage-aware solver smoke test')
    p_tet4.add_argument('--out', default='exports/tet4_stage_smoke.json', help='JSON summary path')
    p_tet4.set_defaults(func=_cmd_tet4_smoke)

    p_pit_tet4 = sub.add_parser('pit-tet4-smoke', help='Run the headless foundation-pit Tet4 staged excavation smoke test')
    p_pit_tet4.add_argument('--out', default='exports/pit_tet4_stage_smoke.json', help='JSON summary path')
    p_pit_tet4.add_argument('--result-dir', default='exports/pit_tet4_results', help='Stage result package directory')
    p_pit_tet4.set_defaults(func=_cmd_pit_tet4_smoke)

    p_result_info = sub.add_parser('result-package-info', help='Inspect a stage result package manifest and GUI/contact indexes')
    p_result_info.add_argument('path', help='Result package directory or manifest.json path')
    p_result_info.set_defaults(func=_cmd_result_package_info)

    p_preview = sub.add_parser("result-preview", help="Preview one array field from a stage result package and optionally export CSV")
    p_preview.add_argument("path", help="Result package directory or manifest.json path")
    p_preview.add_argument("--stage", default=None, help="Stage name to preview")
    p_preview.add_argument("--field", default=None, help="Field name to preview")
    p_preview.add_argument("--rows", type=int, default=12, help="Number of rows to print")
    p_preview.add_argument("--csv", default=None, help="Optional CSV output path")
    p_preview.add_argument("--csv-rows", type=int, default=5000, help="Maximum CSV rows to export")
    p_preview.set_defaults(func=_cmd_result_preview)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, 'func'):
        parser.print_help()
        return 0
    return int(args.func(args))


def gui_main() -> int:
    """Entry point for the GUI console script."""
    return main(['gui'])


if __name__ == '__main__':
    raise SystemExit(main())
