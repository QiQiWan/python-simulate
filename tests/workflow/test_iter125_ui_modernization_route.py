from __future__ import annotations

from geoai_simkit.app.shell.modern_phase_theme import (
    build_modern_phase_ui_contract,
    build_next_optimization_roadmap,
    modern_phase_cards,
    modern_phase_workbench_stylesheet,
    phase_visual_token,
)
from geoai_simkit.app.shell.phase_workbench_qt import build_phase_workbench_qt_payload


def test_modern_phase_ui_contract_exposes_cards_quality_gates_and_roadmap() -> None:
    contract = build_modern_phase_ui_contract("mesh")
    assert contract["contract"] == "modern_phase_workbench_ui_v1"
    assert contract["active_phase"] == "mesh"
    assert len(contract["phase_cards"]) == 6
    assert any(card["active"] and card["key"] == "mesh" for card in contract["phase_cards"])
    assert len(contract["layout_regions"]) >= 7
    assert any("旧版" in gate for gate in contract["quality_gates"])
    assert build_next_optimization_roadmap()[0]["milestone"] == "1.2.5"


def test_phase_cards_have_visual_tokens_and_outputs() -> None:
    cards = modern_phase_cards("results")
    assert [card["key"] for card in cards] == ["geology", "structures", "mesh", "staging", "solve", "results"]
    assert all(card["icon"] for card in cards)
    assert all(card["accent"].startswith("#") for card in cards)
    assert all(card["primary_output"] for card in cards)
    assert phase_visual_token("solve").accent.startswith("#")


def test_phase_qt_payload_includes_modern_ui_without_breaking_launcher_contract() -> None:
    payload = build_phase_workbench_qt_payload("structures")
    assert payload["contract"] == "phase_workbench_qt_payload_v1"
    assert payload["active_phase"] == "structures"
    assert payload["modern_ui"]["contract"] == "modern_phase_workbench_ui_v1"
    assert len(payload["phase_cards"]) == 6
    assert payload["launcher_fix"]["default_when_pyvista_missing"] == "launch_phase_workbench_qt"
    assert payload["launcher_fix"]["legacy_flat_editor_default"] is False
    assert payload["next_optimization_roadmap"][-1]["milestone"] == "1.3.0"


def test_modern_stylesheet_contains_phase_card_and_panel_selectors() -> None:
    stylesheet = modern_phase_workbench_stylesheet()
    assert "QToolButton#phase-card" in stylesheet
    assert "QFrame#modern-header" in stylesheet
    assert "QFrame#panel-card" in stylesheet
