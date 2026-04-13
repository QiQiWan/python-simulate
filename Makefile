.PHONY: install install-ui install-ifc install-warp install-dev demo gui check test

install:
	python -m pip install -r requirements.txt

install-ui:
	python -m pip install -r requirements-ui.txt

install-ifc:
	python -m pip install -r requirements-ifc.txt

install-warp:
	python -m pip install -r requirements-warp.txt

install-dev:
	python -m pip install -r requirements-dev.txt

demo:
	python run_demo.py

gui:
	python run_gui.py

check:
	python run_checks.py

test:
	PYTHONPATH=src pytest -q

install-solver:
	python -m pip install -r requirements-solver.txt

install-meshing:
	python -m pip install -r requirements-meshing.txt
