from __future__ import annotations

from tools._no_install_bootstrap import bootstrap
bootstrap()

from geoai_simkit.cli import main

if __name__ == '__main__':
    raise SystemExit(main(['gui']))
