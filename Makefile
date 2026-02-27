.PHONY: build check-python check-rust check-parity check-all fmt test codeql-local

LANGS ?= python,javascript-typescript
NO_FAIL ?= 0

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

codeql-local:
	@NO_FAIL_FLAG=""; \
	case "$(NO_FAIL)" in 1|true|yes) NO_FAIL_FLAG="--no-fail";; esac; \
	echo "Running CodeQL locally for languages: $(LANGS)"; \
	bash tools/run_codeql_local.sh --lang "$(LANGS)" $$NO_FAIL_FLAG
