from __future__ import annotations

from dataclasses import dataclass

from geoai_simkit.core.model import BoundaryCondition


@dataclass(frozen=True, slots=True)
class BoundaryConditionSpec:
    name: str
    kind: str
    target: str
    components: tuple[int, ...]
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class BoundaryPresetDefinition:
    key: str
    label: str
    description: str
    conditions: tuple[BoundaryConditionSpec, ...]


_BOUNDARY_PRESETS: tuple[BoundaryPresetDefinition, ...] = (
    BoundaryPresetDefinition(
        key='pit_rigid_box',
        label='基坑-刚性箱体（底部+四周 xyz=0）',
        description='最稳健的演示模板：底部和四周边界全部固定三个平移分量，适合先把示例跑通。',
        conditions=(
            BoundaryConditionSpec('fix_bottom', 'displacement', 'bottom', (0, 1, 2), (0.0, 0.0, 0.0)),
            BoundaryConditionSpec('fix_xmin', 'displacement', 'xmin', (0, 1, 2), (0.0, 0.0, 0.0)),
            BoundaryConditionSpec('fix_xmax', 'displacement', 'xmax', (0, 1, 2), (0.0, 0.0, 0.0)),
            BoundaryConditionSpec('fix_ymin', 'displacement', 'ymin', (0, 1, 2), (0.0, 0.0, 0.0)),
            BoundaryConditionSpec('fix_ymax', 'displacement', 'ymax', (0, 1, 2), (0.0, 0.0, 0.0)),
        ),
    ),
    BoundaryPresetDefinition(
        key='pit_bottom_rollers',
        label='基坑-常用简化（底部 xyz=0，侧边法向=0）',
        description='更接近常见土体边界：底部固定 xyz，x 两侧仅限位 x，y 两侧仅限位 y。',
        conditions=(
            BoundaryConditionSpec('fix_bottom', 'displacement', 'bottom', (0, 1, 2), (0.0, 0.0, 0.0)),
            BoundaryConditionSpec('roller_xmin', 'roller', 'xmin', (0,), (0.0,)),
            BoundaryConditionSpec('roller_xmax', 'roller', 'xmax', (0,), (0.0,)),
            BoundaryConditionSpec('roller_ymin', 'roller', 'ymin', (1,), (0.0,)),
            BoundaryConditionSpec('roller_ymax', 'roller', 'ymax', (1,), (0.0,)),
        ),
    ),
    BoundaryPresetDefinition(
        key='bottom_only',
        label='仅底部固定（底部 xyz=0）',
        description='仅适合快速试算或和额外 stage 边界组合使用；单独使用时需要自行补侧边约束。',
        conditions=(
            BoundaryConditionSpec('fix_bottom', 'displacement', 'bottom', (0, 1, 2), (0.0, 0.0, 0.0)),
        ),
    ),
)

DEFAULT_GLOBAL_BOUNDARY_PRESET_KEY = 'pit_rigid_box'
DEFAULT_STAGE_BOUNDARY_PRESET_KEY = 'pit_rigid_box'


def available_boundary_presets() -> tuple[BoundaryPresetDefinition, ...]:
    return _BOUNDARY_PRESETS


def boundary_preset_definition(key: str) -> BoundaryPresetDefinition:
    for item in _BOUNDARY_PRESETS:
        if item.key == key:
            return item
    raise KeyError(f'Unknown boundary preset: {key}')


def build_boundary_conditions_from_preset(key: str) -> list[BoundaryCondition]:
    preset = boundary_preset_definition(key)
    result: list[BoundaryCondition] = []
    for spec in preset.conditions:
        result.append(
            BoundaryCondition(
                name=spec.name,
                kind=spec.kind,
                target=spec.target,
                components=tuple(spec.components),
                values=tuple(spec.values),
                metadata={'preset': True, 'preset_key': preset.key, 'preset_label': preset.label},
            )
        )
    return result
