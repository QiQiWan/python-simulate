# Contributing

## Development setup

```bash
python -m pip install -e .[all,dev]
```

## Before opening a change

Run the following locally:

```bash
pytest -q
python -m build
python -m twine check dist/*
```

## Style

- keep comments and docstrings in English
- prefer small, targeted changes with tests
- add or update tests when fixing behavioral bugs
- preserve optional-dependency guards for GUI/IFC/gpu-only features

## Commit scope

A good change usually includes:

- the code update
- a test or smoke check covering it
- documentation updates when behavior changes
