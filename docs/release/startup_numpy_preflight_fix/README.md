# Startup dependency preflight fix for broken NumPy installs

This patch hardens the GUI launcher against environments where `import numpy`
succeeds but the imported module is not a valid NumPy runtime, for example:

```text
module 'numpy' has no attribute 'ndarray'
```

## What changed

- The startup preflight now validates required API attributes, not just module import/version.
- NumPy must expose `ndarray`, `array`, `asarray`, and `zeros`.
- Broken or shadowed modules now appear as `BROKEN` in the preflight report.
- The report includes the imported module path so local files such as `numpy.py` can be identified.
- The startup dialog shows problem details and repair commands before entering the main GUI.
- The top-level launcher prints the dependency report and explicit recovery commands if startup still fails.

## Recommended recovery for users

```powershell
python -m pip install --upgrade --force-reinstall numpy scipy
python -m pip install -r requirements.txt
```

If the preflight report says NumPy was imported from a project-local path such as
`E:\...\numpy.py`, rename or remove that file/folder because it shadows the real package.
