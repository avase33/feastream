.PHONY: up down test test-rust test-go test-python build-web demo eval verify

up:
	docker compose up --build

down:
	docker compose down

test: test-rust test-go test-python

test-rust:
	cd compute-rust && cargo test

test-go:
	cd gateway-go && go test ./...

test-python:
	cd inference-python && pip install -e ".[dev]" && pytest -q

build-web:
	cd cockpit-ts && npm install && npm run build

# Offline: train the from-scratch GBDT and score a calm vs a fraud vector.
demo:
	cd inference-python && python -m feastream_infer.cli demo

eval:
	cd inference-python && python -m feastream_infer.cli eval

verify:
	python scripts/verify.py
