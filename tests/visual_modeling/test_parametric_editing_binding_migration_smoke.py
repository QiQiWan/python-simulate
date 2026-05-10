from __future__ import annotations

from tools.run_parametric_editing_binding_migration_smoke import main


def test_parametric_editing_binding_migration_smoke() -> None:
    assert main() == 0
