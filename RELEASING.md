# Releasing geoai-simkit

## Local checklist

1. Update `src/geoai_simkit/_version.py`.
2. Summarize user-facing changes in `CHANGELOG.md`.
3. Run tests:

   ```bash
   pytest -q
   ```

4. Build distributions:

   ```bash
   python -m pip install -e .[dev]
   python -m build
   python -m twine check dist/*
   ```

5. Smoke-check the installed CLI in a clean environment when possible.

## GitHub publishing

- `ci.yml` builds and tests the package on pushes and pull requests.
- `publish.yml` is prepared for PyPI/TestPyPI Trusted Publishing.
- Before enabling the publish workflow, replace placeholder package URLs and configure the matching PyPI trusted publishers.

## Final manual checks

- verify the README renders correctly on the package index
- confirm optional extras install cleanly
- confirm GUI launch on a desktop-capable machine
- confirm gmsh/OpenGL system libraries on Linux workstations
- choose and add the final project license before a public open-source release
