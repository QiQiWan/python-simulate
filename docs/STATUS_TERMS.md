# Status-driven wording policy

Avoid broad claims such as `production`, `commercial`, or `fully resident` unless the code has the corresponding evidence.

Use these terms instead:

| Use | Meaning |
|---|---|
| `usable_core` | Main workflow feature with validation and failure metadata. |
| `benchmark_grade` | Numerically useful and covered by a benchmark, but not certification-grade. |
| `research_scaffold` | Useful architecture or algorithm scaffold; not yet enough verification. |
| `capability_probe` | Optional hardware/dependency path that must be verified at runtime. |
| `certification_pending` | Has a benchmark book scaffold, but official references are missing. |
| `gpu_residency_gated` | GPU path exists, but is accepted only when CPU fallback is not used. |

This policy is reflected in benchmark report display names and GUI payload metadata.
