from __future__ import annotations

import numpy as np

from geoai_simkit.app.ifc_suggestions import apply_suggestion_subset, build_suggestions
from geoai_simkit.core.model import GeometryObjectRecord, MaterialDefinition, SimulationModel
from geoai_simkit.core.types import RegionTag


def test_build_suggestions_maps_ifc_wall_to_wall_material():
    model = SimulationModel(name='m', mesh=None)  # type: ignore[arg-type]
    model.region_tags = [RegionTag(name='wall_region', cell_ids=np.asarray([], dtype=np.int64))]
    model.object_records = [GeometryObjectRecord(key='o1', name='Wall A', object_type='IfcWall', region_name='wall_region')]
    model.material_library = [
        MaterialDefinition(name='Wall_Elastic', model_type='linear_elastic', parameters={}),
        MaterialDefinition(name='Soil_MC', model_type='mohr_coulomb', parameters={}),
    ]
    suggestions = build_suggestions(model)
    assert suggestions[0].role == 'wall'
    assert suggestions[0].material_definition == 'Wall_Elastic'


def test_build_suggestions_maps_ifc_beam_to_beam_role():
    model = SimulationModel(name='m', mesh=None)  # type: ignore[arg-type]
    model.object_records = [GeometryObjectRecord(key='o1', name='Strut-1', object_type='IfcBeam')]
    suggestions = build_suggestions(model)
    assert suggestions[0].role == 'beam'



def test_apply_suggestion_subset_only_applies_checked_items():
    model = SimulationModel(name='m', mesh=None)  # type: ignore[arg-type]
    model.region_tags = [
        RegionTag(name='wall_region', cell_ids=np.asarray([], dtype=np.int64)),
        RegionTag(name='soil_region', cell_ids=np.asarray([], dtype=np.int64)),
    ]
    model.object_records = [
        GeometryObjectRecord(key='o1', name='Wall A', object_type='IfcWall', region_name='wall_region'),
        GeometryObjectRecord(key='o2', name='Soil A', object_type='IfcBuildingElementProxy', region_name='soil_region'),
    ]
    model.material_library = [
        MaterialDefinition(name='Wall_Elastic', model_type='linear_elastic', parameters={}),
        MaterialDefinition(name='Soil_MC', model_type='mohr_coulomb', parameters={}),
    ]
    suggestions = build_suggestions(model)
    applied = apply_suggestion_subset(model, suggestions, accepted_keys=['o1'], assign_materials=True)
    assert len(applied) == 1
    assert model.object_record('o1').metadata['role'] == 'wall'
    assert model.material_for_region('wall_region').material_name == 'linear_elastic'
    assert model.object_record('o2').metadata.get('role') is None
