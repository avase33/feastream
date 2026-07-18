FROM rust:1.79-slim AS build
WORKDIR /app
COPY Cargo.toml ./
COPY src ./src
COPY tests ./tests
RUN cargo build --release --bin feastream-compute

FROM debian:bookworm-slim
COPY --from=build /app/target/release/feastream-compute /usr/local/bin/feastream-compute
ENV FEASTREAM_COMPUTE_ADDR=0.0.0.0:8091
EXPOSE 8091
CMD ["feastream-compute"]
