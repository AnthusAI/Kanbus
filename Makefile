.PHONY: build check-python check-rust check-parity check-all fmt test

build:
	cd packages/ui && npm install && npm run build
	cd apps/console && npm install && npm run build
	cd rust && cargo install --path .

check-python:
	cd python && black --check .
	cd python && ruff check .
	cd python && behave

check-rust:
	cd rust && cargo fmt --check
	cd rust && cargo clippy -- -D warnings
	cd rust && cargo test

check-parity:
	python tools/check_spec_parity.py

check-all: check-python check-rust check-parity

fmt:
	cd python && black .
	cd python && ruff check . --fix
	cd rust && cargo fmt

test:
	cd python && behave
	cd rust && cargo test
