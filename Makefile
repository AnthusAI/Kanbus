.PHONY: check-python check-rust check-parity check-all fmt test

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
