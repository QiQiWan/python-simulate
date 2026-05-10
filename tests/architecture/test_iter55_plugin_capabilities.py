from __future__ import annotations


def test_all_plugin_catalog_entries_have_unified_health_and_capabilities() -> None:
    from geoai_simkit.modules import module_plugin_catalog

    catalog = module_plugin_catalog()
    assert catalog
    for category, rows in catalog.items():
        assert rows, category
        for row in rows:
            assert row["key"]
            assert row["category"]
            assert "available" in row
            assert isinstance(row["capabilities"], dict)
            assert isinstance(row["health"], dict)
            assert "status" in row["health"]


def test_dummy_plugins_can_be_registered_resolved_and_used_without_gui_or_services() -> None:
    from geoai_simkit.adapters import make_project_context
    from geoai_simkit.modules import document_model
    from geoai_simkit.modules.example_plugins import DummyMeshGenerator, DummyPostProcessor, DummySolverBackend
    from geoai_simkit.modules.fem_solver import register_solver_backend, solve_project
    from geoai_simkit.modules.meshing import generate_project_mesh, register_mesh_generator
    from geoai_simkit.modules.postprocessing import register_postprocessor, summarize_results

    project = document_model.create_foundation_pit_project({"dimension": "3d"}, name="dummy-plugin")
    port = make_project_context(project)

    register_mesh_generator(DummyMeshGenerator(), replace=True)
    register_solver_backend(DummySolverBackend(), replace=True)
    register_postprocessor(DummyPostProcessor(), replace=True)

    mesh = generate_project_mesh(port, mesh_kind="dummy_mesh", attach=False)
    solve = solve_project(port, backend_preference="dummy_solver")
    summary = summarize_results(object(), processor="dummy_postprocessor", stage_ids=("s1",), fields=("u",))

    assert mesh.ok is True
    assert solve.backend_key == "dummy_solver"
    assert summary.metadata["plugin"] == "dummy_postprocessor"
