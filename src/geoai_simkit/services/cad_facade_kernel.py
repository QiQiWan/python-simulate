from __future__ import annotations

"""CAD facade public API for 1.4.2a.

The implementation currently lives in ``native_cad_occ_kernel`` for backward
compatibility with earlier workbench imports. New code should import from this
module to avoid implying certified native BRep behaviour.
"""

from geoai_simkit.services.native_cad_occ_kernel import (  # noqa: F401
    CadFeatureExecutionReport,
    CadOccCapabilityReport,
    CadTopologyIndexReport,
    build_cad_topology_index,
    execute_deferred_cad_features,
    probe_native_cad_occ_kernel,
)


def probe_cad_facade_kernel() -> CadOccCapabilityReport:
    return probe_native_cad_occ_kernel()


__all__ = [
    "CadFeatureExecutionReport",
    "CadOccCapabilityReport",
    "CadTopologyIndexReport",
    "build_cad_topology_index",
    "execute_deferred_cad_features",
    "probe_cad_facade_kernel",
    "probe_native_cad_occ_kernel",
]
