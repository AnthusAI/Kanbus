FROM rust:1.89-bookworm AS build
WORKDIR /workspace

COPY . /workspace
RUN cargo build --release --bin console_lambda

FROM public.ecr.aws/lambda/provided:al2023
COPY --from=build /workspace/target/release/console_lambda /var/task/bootstrap
COPY --from=build /workspace/embedded_assets/console /opt/apps/console/dist
CMD ["bootstrap"]
