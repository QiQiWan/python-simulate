from __future__ import annotations

"""Engineering demo templates for the 1.4.0 Beta-2 workbench.

The 1.3 line proved a single one-click foundation-pit demo.  1.4.0 promotes
that capability to a small template catalog.  Each template intentionally uses
one auditable calculation stack while adding template-specific identity,
workflow phases, engineering checks and result targets.  The service is kept
lightweight so it can be imported by GUI payload builders without requiring Qt,
Gmsh or PyVista.
"""

from dataclasses import dataclass, field
from typing import Any


PHASE_SEQUENCE = ["geology", "structures", "mesh", "staging", "solve", "results"]


@dataclass(slots=True)
class EngineeringDemoTemplate:
    demo_id: str
    label: str
    short_label: str
    template_family: str
    description: str
    primary_engineering_question: str
    phase_names: dict[str, str]
    expected_outputs: list[str] = field(default_factory=list)
    result_targets: list[str] = field(default_factory=list)
    one_click_load: bool = True
    complete_calculation: bool = True
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "demo_id": self.demo_id,
            "label": self.label,
            "short_label": self.short_label,
            "release": "1.4.2a-cad-facade",
            "template_family": self.template_family,
            "description": self.description,
            "primary_engineering_question": self.primary_engineering_question,
            "phase_sequence": list(PHASE_SEQUENCE),
            "phase_names": dict(self.phase_names),
            "expected_outputs": list(self.expected_outputs),
            "result_targets": list(self.result_targets),
            "one_click_load": bool(self.one_click_load),
            "complete_calculation": bool(self.complete_calculation),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }


TEMPLATE_SPECS: dict[str, EngineeringDemoTemplate] = {
    "foundation_pit_3d_beta": EngineeringDemoTemplate(
        demo_id="foundation_pit_3d_beta",
        label="三维基坑分阶段施工 Beta Demo",
        short_label="基坑",
        template_family="foundation_pit",
        description="围护墙、支撑、开挖失活、地下水和结果导出的六阶段基坑模板。",
        primary_engineering_question="分阶段开挖和支护激活后，墙体位移、沉降和孔压响应是否可接受？",
        phase_names={
            "initial": "初始地应力",
            "excavation_1": "第一次开挖",
            "support_1": "第一道支撑",
            "excavation_2": "第二次开挖",
            "support_2": "第二道支撑",
        },
        expected_outputs=["墙体水平位移", "地表沉降", "支撑轴力", "孔压变化", "VTK 云图"],
        result_targets=["max_displacement", "max_settlement", "plastic_point", "pore_pressure", "interface_contact_state"],
        tags=["excavation", "retaining_wall", "strut", "groundwater"],
        metadata={"recommended_template": True, "geometry_basis": "axis_aligned_foundation_pit"},
    ),
    "slope_stability_beta": EngineeringDemoTemplate(
        demo_id="slope_stability_beta",
        label="边坡稳定分阶段降雨 Beta Demo",
        short_label="边坡",
        template_family="slope_stability",
        description="边坡土体、坡脚开挖、降雨/水位条件和安全响应检查的六阶段模板。",
        primary_engineering_question="坡脚扰动和水位变化后，塑性区、位移和有效应力响应是否提示失稳风险？",
        phase_names={
            "initial": "边坡初始应力",
            "excavation_1": "坡脚扰动",
            "support_1": "抗滑桩/加固激活",
            "excavation_2": "降雨工况",
            "support_2": "长期稳定校核",
        },
        expected_outputs=["潜在滑动区", "坡顶位移", "孔压上升", "有效应力降低", "安全审查摘要"],
        result_targets=["plastic_point", "degree_of_consolidation", "effective_stress_zz", "max_displacement"],
        tags=["slope", "rainfall", "stability", "reinforcement"],
        metadata={"template_role": "stability_screening", "geometry_basis": "surrogate_slope_mass"},
    ),
    "pile_soil_interaction_beta": EngineeringDemoTemplate(
        demo_id="pile_soil_interaction_beta",
        label="桩-土相互作用加载 Beta Demo",
        short_label="桩土",
        template_family="pile_soil_interaction",
        description="桩基、桩周土、界面接触和加载响应的六阶段模板。",
        primary_engineering_question="竖向/水平加载后，桩顶位移、桩周界面状态和土体塑性响应是否满足要求？",
        phase_names={
            "initial": "桩周土初始应力",
            "excavation_1": "成桩/安装阶段",
            "support_1": "桩土界面激活",
            "excavation_2": "竖向加载",
            "support_2": "水平加载与服务性校核",
        },
        expected_outputs=["桩顶位移", "桩周界面滑移", "土体塑性区", "桩身受力指标", "VTK 云图"],
        result_targets=["interface_gap", "interface_shear_slip", "plastic_point", "max_displacement"],
        tags=["pile", "soil_structure_interaction", "contact", "loading"],
        metadata={"template_role": "soil_structure_interaction", "geometry_basis": "surrogate_pile_cluster"},
    ),
}


def get_engineering_template_spec(demo_id: str) -> EngineeringDemoTemplate:
    try:
        return TEMPLATE_SPECS[str(demo_id)]
    except KeyError as exc:
        raise ValueError(f"Unknown engineering demo id: {demo_id}") from exc


def list_engineering_templates() -> list[EngineeringDemoTemplate]:
    return [TEMPLATE_SPECS[key] for key in TEMPLATE_SPECS]


def build_engineering_template_catalog() -> dict[str, Any]:
    templates = [spec.to_dict() for spec in list_engineering_templates()]
    return {
        "contract": "geoai_simkit_engineering_template_catalog_v1",
        "release": "1.4.2a-cad-facade",
        "default_demo_id": "foundation_pit_3d_beta",
        "template_count": len(templates),
        "templates": templates,
        "demos": templates,
        "actions": ["load_demo_project", "run_complete_calculation", "export_demo_bundle", "run_all_templates"],
        "quality_gate": {
            "all_templates_must_load": True,
            "all_templates_must_complete_pipeline": True,
            "all_templates_must_export_bundle": True,
        },
    }


def apply_engineering_template_identity(project: Any, demo_id: str) -> dict[str, Any]:
    """Attach 1.4.0 template identity and phase names to an existing project."""

    spec = get_engineering_template_spec(demo_id)
    project.project_settings.name = f"GeoAI SimKit 1.4.0 Beta-2 {spec.label}"
    project.project_settings.metadata.update({
        "release": "1.4.2a-cad-facade",
        "workflow": f"template_{spec.template_family}",
        "demo_id": spec.demo_id,
        "template_family": spec.template_family,
    })
    project.metadata["release"] = "1.4.2a-cad-facade"
    project.metadata["release_line"] = "1.4.x"
    project.metadata["active_demo_id"] = spec.demo_id
    project.metadata["active_template_family"] = spec.template_family
    project.metadata["release_1_4_0_demo"] = {
        "contract": "geoai_simkit_release_1_4_0_demo_metadata_v1",
        **spec.to_dict(),
    }
    # Rename phases for the selected engineering narrative while preserving ids
    # used by the solver/compiler tests and stage snapshots.
    for phase_id, phase_name in spec.phase_names.items():
        try:
            phase = project.get_phase(phase_id)
            phase.name = phase_name
            phase.metadata.update({"template_family": spec.template_family, "demo_id": spec.demo_id})
        except Exception:
            continue
    for phase_id in project.phase_ids():
        try:
            project.refresh_phase_snapshot(phase_id)
            snapshot = project.phase_manager.phase_state_snapshots.get(phase_id)
            if snapshot is not None:
                snapshot.metadata.update({"template_family": spec.template_family, "demo_id": spec.demo_id})
        except Exception:
            continue
    # Template-specific presentation hints.  The calculation stack remains the
    # same auditable six-phase stack; the semantic hints guide GUI/report views.
    project.geometry_model.metadata.update({"template_family": spec.template_family, "demo_id": spec.demo_id})
    project.structure_model.metadata.update({"template_family": spec.template_family, "demo_id": spec.demo_id})
    project.mesh_model.metadata["template_family"] = spec.template_family
    project.result_store.metadata.update({"template_family": spec.template_family, "demo_id": spec.demo_id, "result_targets": list(spec.result_targets)})
    project.solver_model.metadata.setdefault("template_engineering_targets", {})[spec.demo_id] = {
        "primary_engineering_question": spec.primary_engineering_question,
        "result_targets": list(spec.result_targets),
        "expected_outputs": list(spec.expected_outputs),
    }
    if spec.template_family == "slope_stability":
        project.solver_model.metadata["slope_stability_control"] = {
            "contract": "geoai_simkit_slope_stability_control_v1",
            "rainfall_phase_id": "excavation_2",
            "checks": ["plastic_zone_growth", "pore_pressure_rise", "crest_displacement"],
        }
    if spec.template_family == "pile_soil_interaction":
        project.solver_model.metadata["pile_soil_interaction_control"] = {
            "contract": "geoai_simkit_pile_soil_interaction_control_v1",
            "loading_phases": ["excavation_2", "support_2"],
            "checks": ["pile_head_displacement", "interface_slip", "soil_plasticity"],
        }
    return project.metadata["release_1_4_0_demo"]


__all__ = [
    "PHASE_SEQUENCE",
    "EngineeringDemoTemplate",
    "TEMPLATE_SPECS",
    "get_engineering_template_spec",
    "list_engineering_templates",
    "build_engineering_template_catalog",
    "apply_engineering_template_identity",
]
