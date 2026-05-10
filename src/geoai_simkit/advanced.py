from __future__ import annotations

"""Advanced capability matrix with truthful optional-backend gates."""


def advanced_matrix() -> list[dict[str, object]]:
    return [
        {
            "key": "gpu",
            "label": "GPU resident solver probes",
            "status": "capability_probe",
            "namespace": "geoai_simkit.solver.gpu_*",
            "truthful_gate": "gpu_resident_ran=false falls back to CPU reference unless require_gpu=True",
        },
        {
            "key": "occ",
            "label": "OCC/BRep topology probes",
            "status": "capability_probe",
            "namespace": "geoai_simkit.solver.contact.occ_*",
            "truthful_gate": "native_occ_end_to_end only when pythonocc-core is installed",
        },
        {
            "key": "uq",
            "label": "Uncertainty and calibration reports",
            "status": "capability_probe",
            "namespace": "geoai_simkit.solver.material_*",
            "truthful_gate": "deterministic reference reports are used when full UQ datasets are unavailable",
        },
    ]


__all__ = ["advanced_matrix"]
