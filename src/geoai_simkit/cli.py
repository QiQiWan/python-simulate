from __future__ import annotations

import argparse
from pathlib import Path

from geoai_simkit.env_check import collect_environment_checks, format_environment_report


def _run_demo(out_dir: Path) -> None:
    from geoai_simkit.examples.pit_example import run_demo
    out = run_demo(out_dir)
    print(out)


def _run_gui() -> None:
    from geoai_simkit.app.main_window import launch_main_window
    launch_main_window()


def main() -> None:
    parser = argparse.ArgumentParser(prog="geoai-simkit")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="Launch the Qt/PyVista GUI")

    demo = sub.add_parser("demo", help="Run the packaged pit demo")
    demo.add_argument("--out-dir", default="exports")

    sub.add_parser("check-env", help="Show optional dependency availability")

    args = parser.parse_args()

    if args.cmd == "check-env":
        print(format_environment_report(collect_environment_checks()))
        return
    if args.cmd == "gui":
        _run_gui()
        return
    _run_demo(Path(getattr(args, "out_dir", "exports")))


if __name__ == "__main__":
    main()
