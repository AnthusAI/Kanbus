# Asset revision: 2026-03-29 repo-root console build
FROM node:20.17.0-bookworm AS console-build
WORKDIR /workspace

COPY packages/ui ./packages/ui
WORKDIR /workspace/packages/ui
RUN npm ci
RUN npm run build

WORKDIR /workspace
COPY apps/console ./apps/console

WORKDIR /workspace/apps/console
RUN npm ci
RUN npm run build

FROM rust:1.89-bookworm AS build
WORKDIR /workspace/rust

COPY rust/Cargo.toml rust/Cargo.lock rust/build.rs ./
COPY rust/features ./features
COPY rust/src ./src
COPY rust/tests ./tests
RUN cargo build --release --bin console_lambda

FROM public.ecr.aws/lambda/provided:al2023
COPY --from=build /workspace/rust/target/release/console_lambda /var/runtime/bootstrap
COPY --from=console-build /workspace/apps/console/dist /opt/apps/console/dist
RUN chmod +x /var/runtime/bootstrap
CMD ["bootstrap"]
