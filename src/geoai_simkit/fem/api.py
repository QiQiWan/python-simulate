from __future__ import annotations
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from typing import Any
from geoai_simkit.fem.numerical_smoke import run_core_numerical_smoke, run_single_smoke

@dataclass(frozen=True, slots=True)
class FEMAPIContract:
    key: str
    label: str
    stage_index: int
    target_namespace: str
    public_entrypoints: tuple[str, ...]
    input_contract: str
    output_contract: str
    status: str = 'benchmark_grade'
    def to_dict(self) -> dict[str, Any]: return asdict(self)

def dependency_light_smoke(contract: FEMAPIContract) -> dict[str, Any]:
    root_name = contract.target_namespace.split()[0].split('/')[0].split('.')[0]
    spec_available = find_spec(root_name) is not None
    entrypoints_ok = bool(contract.public_entrypoints)
    return {'key': contract.key, 'label': contract.label, 'target_namespace': contract.target_namespace, 'ok': bool(spec_available and entrypoints_ok), 'spec_available': bool(spec_available), 'entrypoints': list(contract.public_entrypoints), 'status': contract.status}

CORE_FEM_API_CONTRACTS: tuple[FEMAPIContract, ...] = (
    FEMAPIContract('geometry','Geometry',1,'geoai_simkit.geometry',('build/edit topology','select block/face/region'),'CAD/topology objects','named solids, faces and stage objects'),
    FEMAPIContract('mesh','Mesh',2,'geoai_simkit.geometry.mesh_engine',('mesh generation','mesh quality gate'),'geometry/topology','nodes, elements, tags and quality report'),
    FEMAPIContract('material','Material',3,'geoai_simkit.materials',('stress update','state variables','tangent'),'strain increment and state','stress, tangent and updated state'),
    FEMAPIContract('element','Element',4,'geoai_simkit.solver',('Tet4','Hex8','truss/beam/shell'),'mesh + material','element residual/stiffness and integration state'),
    FEMAPIContract('assembly','Assembly',5,'geoai_simkit.solver.linsys',('CSR assembly','constraints','load vector'),'element contributions','global sparse system'),
    FEMAPIContract('solver','Solver',6,'geoai_simkit.solver',('linear solve','Newton/Krylov','strict fallback policy'),'global system and settings','displacement/state/result metadata'),
    FEMAPIContract('result','Result',7,'geoai_simkit.results',('result package','acceptance gate','benchmark fragment'),'solver output','auditable result package'),
)

def get_core_fem_api_contracts() -> list[dict[str, Any]]: return [item.to_dict() for item in CORE_FEM_API_CONTRACTS]
def run_core_fem_api_smoke() -> dict[str, Any]: return run_core_numerical_smoke()
def run_core_fem_module_smoke(key: str) -> dict[str, Any]: return run_single_smoke(key)
