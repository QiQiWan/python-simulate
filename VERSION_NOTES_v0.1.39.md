# v0.1.39

- Fix nonlinear structural assembly crash on CPU by handling `StructuralAssemblyResult` correctly in `NonlinearHex8Solver._evaluate_state`.
- Make demo stage filtering respect per-stage `active_support_groups` and `active_interface_groups`.
- Populate demo stages with explicit active support/interface groups so the initial stage keeps only wall + crown beam and later stages activate struts progressively.
- Keep stage notes clearer for staged support activation.
