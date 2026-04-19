from geoai_simkit.solver.constitutive import ConstitutiveKernelRegistry, ConstitutiveModelDescriptor
from geoai_simkit.solver.gpu import DeviceMemoryPool, KernelRegistry
from geoai_simkit.solver.linsys import LinearSystemOperator, PreconditionerSpec, SparseBlockMatrix
from geoai_simkit.solver.operators import (
    BoundaryOperator,
    ContactOperator,
    ContinuumHex8Operator,
    InterfaceOperator,
    OperatorContext,
    StructuralOperator,
)


def test_solver_runtime_scaffolding_imports_and_basic_contracts() -> None:
    context = OperatorContext(stage_name='initial')
    assert BoundaryOperator().evaluate({}, context).diagnostics['operator'] == 'boundary'
    assert ContinuumHex8Operator().evaluate({}, context).diagnostics['operator'] == 'continuum_hex8'
    structural = StructuralOperator().evaluate(
        {
            'count': 1,
            'kind_counts': {'truss2': 1},
            'dof_summary': {'total_dof_count': 12},
            'linear_system_summary': {'shape': [12, 12], 'block_size': 3, 'nnz_entries': 12},
        },
        context,
    ).diagnostics
    interface = InterfaceOperator().evaluate(
        {
            'count': 1,
            'kind_counts': {'node_pair': 1},
            'linear_system_summary': {'shape': [12, 12], 'block_size': 3, 'nnz_entries': 12},
        },
        context,
    ).diagnostics
    contact = ContactOperator().evaluate({'count': 1, 'closed_pair_count': 1}, context).diagnostics
    assert structural['active_structure_count'] == 1
    assert interface['active_interface_count'] == 1
    assert contact['active_contact_pair_count'] == 1

    descriptor = ConstitutiveModelDescriptor(
        name='soil',
        model_type='linear_elastic',
        parameters={'E': 1.0e7, 'nu': 0.3},
    )
    registry = ConstitutiveKernelRegistry()
    model = registry.create(descriptor)
    assert model.__class__.__name__ == 'LinearElastic'

    pool = DeviceMemoryPool(requested_device='cpu')
    assert pool.snapshot()
    assert isinstance(KernelRegistry().available(), list)
    assert LinearSystemOperator().matrix is None
    assert SparseBlockMatrix().block_size == 1
    assert PreconditionerSpec().name == 'auto'

    matrix_summary = SparseBlockMatrix.from_summary(
        {'shape': [12, 12], 'block_size': 3, 'nnz_entries': 144, 'storage': 'csr'}
    ).summary()
    assert matrix_summary['shape'] == [12, 12]
    assert matrix_summary['block_size'] == 3
    assert matrix_summary['nnz_entries'] == 144

    linear_system = LinearSystemOperator.from_summary(
        {'shape': [12, 12], 'block_size': 3, 'nnz_entries': 144, 'storage': 'csr'},
        metadata={'solver_backend': 'cpu'},
    ).summary()
    assert linear_system['ndof'] == 12
    assert linear_system['matrix']['block_size'] == 3
    assert linear_system['solver_backend'] == 'cpu'
