#!/usr/bin/env bash
set -euo pipefail

echo "Running full CI gate inside Amplify..."

sudo dnf -y update
sudo dnf -y install \
  gcc \
  gcc-c++ \
  make \
  git \
  golang \
  libicu-devel \
  openssl-devel \
  pkgconfig \
  python3.11 \
  python3.11-pip

python3.11 -m pip install --upgrade pip
python3.11 -m pip install -e python
python3.11 -m pip install black ruff coverage
export PATH="$HOME/.local/bin:$PATH"

curl https://sh.rustup.rs -sSf | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"
rustup default stable
rustup component add llvm-tools-preview

cd python
black --check .
ruff check .
mkdir -p ../coverage-python
python3.11 -m coverage run --source=kanbus -m behave
python3.11 -m coverage xml -o ../coverage-python/coverage.xml
cd ..
python3.11 tools/check_spec_parity.py

(cd packages/ui && npm ci && npm run build)
(cd apps/console && npm ci && npm run build)
rm -rf rust/embedded_assets/console
cp -R apps/console/dist rust/embedded_assets/console

cd rust
cargo fmt --check
cargo clippy -- -D warnings
cargo test
cargo install cargo-llvm-cov --locked
mkdir -p ../coverage-rust
cargo llvm-cov --locked --no-report --all-features --lib --bins --tests --ignore-filename-regex "features/steps/.*|src/bin/.*|src/main.rs"
cargo llvm-cov report --locked --cobertura --output-path ../coverage-rust/cobertura.xml
cd ..

cd apps/console
npm ci --prefer-offline --no-audit
npx playwright install --with-deps
npm run test:ui
cd ../..

python3.11 tools/check_benchmarks.py

cd rust
cargo build --release --bin kbs --bin kbsc
cd ..
mkdir -p dist
cp rust/target/release/kbs dist/kbs
cp rust/target/release/kbsc dist/kbsc
tools/test_prebuilt_binaries_docker.sh dist/kbs dist/kbsc

binary=$(python3.11 tools/build_rust_release.py)
python3.11 tools/run_beads_interop_suite.py --rust-binary "$binary"

echo "Amplify CI gate completed."
