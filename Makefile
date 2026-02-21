.PHONY: run install test

install:
	pip3 install --user -r requirements.txt

run:
	python3 run.py

test:
	python3 -m pytest tests/ -v
