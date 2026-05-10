# GeoAI SimKit Iteration 0.8.6 — Consistent Newton / Contact / HSS / Native Assembly

## Scope

This iteration targets the nonlinear solver weak points that blocked the package from moving beyond a demonstrator:

1. consistent-tangent Newton-Raphson;
2. strict frictional contact complementarity;
3. interface-element constitutive law;
4. HSS / HS-small complete state variables;
5. large-scale sparse nonlinear solve reuse;
6. GPU-native nonlinear assembly handoff.

## Main changes

### 1. Consistent-tangent Newton-Raphson

- Added `geoai_simkit.materials.tangent`.
- Added `ConsistentTangentConfig` and `algorithmic_tangent_matrix()`.
- `NonlinearTet4Options` now supports:
  - `use_consistent_tangent`
  - `newton_correction`
  - `correction_line_search`
  - `max_correction_norm_ratio`
  - `consistent_tangent_perturbation`
- `material_update="consistent-newton"` automatically enables consistent tangent and Newton correction.
- Added `geoai_simkit.solver.nonlinear_newton`:
  - tangent triplet assembly;
  - free-DOF Newton correction solve;
  - sparse solve metadata;
  - optional native assembly path.

### 2. Strict frictional contact complementarity

- Replaced the former global xyz penalty spring assumption with local normal/tangent contact assembly.
- Added `CoulombInterfaceMaterial`.
- Contact assembly now reports:
  - open / closed pair counts;
  - stick / slip pair counts;
  - normal multiplier;
  - friction limit;
  - friction violation;
  - normal complementarity violation;
  - diagnostic `pair_rows`.
- Supported active-set modes now include:
  - `open_close`
  - `normal_gap`
  - `strict_frictional`
  - `frictional`
  - `coulomb`
  - `semismooth`
  - `complementarity`

### 3. Interface-element constitutive law

- Added `geoai_simkit.materials.interface`.
- Implemented a small-strain zero-thickness Coulomb interface law with:
  - normal penalty;
  - tangential penalty;
  - friction cone projection;
  - stick/slip state;
  - algorithmic tangent matrix;
  - persistent interface state object.

### 4. HSS / HS-small state variables

- Expanded HSS state schema from a minimal dict to a runtime-packable schema.
- Added scalar history variables:
  - `eps_p_shear`
  - `eps_p_vol`
  - `eps_p_eq`
  - `eps_p_cap`
  - `eps_p_unload`
  - `p_ref_state`
  - `q_ref_state`
  - `p_cap`
  - `preconsolidation_pressure`
  - `ocr`
  - `gamma_hist`
  - `gamma_rev`
  - `gamma_max`
  - `Gsec`
  - `E_loading`
  - `E_oedometer`
  - `E_unloading`
  - `last_dgamma_s`
  - `last_dgamma_c`
  - `last_plastic_multiplier`
- Added array history variables:
  - `backstress`
  - `plastic_strain_tensor`
  - `reversal_strain`
- Added `consistent_tangent_matrix()` for HSS.

### 5. Large sparse nonlinear solve optimization

- Reused `LinearSolverContext` across nonlinear iterations.
- Newton correction now records:
  - solver backend;
  - correction norm;
  - residual norm;
  - free DOF count;
  - contact triplet count;
  - factorization/pattern reuse metadata where available.
- Sparse Krylov iteration reporting now uses callback-based actual iteration counts where SciPy exposes them.

### 6. GPU-native nonlinear assembly

- Added `geoai_simkit.solver.gpu_native_assembly`.
- Provides a stable native assembly contract:
  - `NativeAssemblyResult`
  - `assemble_tet4_triplets_native()`
- Supports optional Torch CUDA element-triplet assembly.
- Falls back to deterministic CPU-native triplet assembly when CUDA is unavailable.
- Integrated with Newton correction using `solver_metadata={"gpu_native_assembly": True}`.

## Verification added

New regression tests:

- `tests/test_consistent_newton_contact_hss_gpu_native.py`

Validated checks:

- HSS state schema and consistent tangent are finite and runtime-packable.
- Strict frictional contact generates local-basis triplets and complementarity diagnostics.
- Interface material projects shear traction to the Coulomb cone.
- Native assembly fallback and Newton correction contract work.
- `material_update="consistent-newton"` enables the new Newton path.

## Known limitations

- The current consistent tangent is local algorithmic / finite-difference backed unless a material exposes a closed-form tangent.
- Contact is still node-pair based; face-to-face integration is prepared by interface-element definitions but not yet a full mortar/Nitsche contact discretization.
- GPU native assembly is optional and depends on Torch CUDA availability; CPU fallback preserves the same solver contract.
