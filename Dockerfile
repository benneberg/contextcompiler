# ── Stage 1: build wheel ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps only in builder stage
RUN pip install --no-cache-dir --upgrade pip build

COPY pyproject.toml README.md LICENSE ./
COPY ccc/ ./ccc/
COPY py.typed ./

# Build a wheel so the runtime stage gets a clean, no-source-code install
RUN python -m build --wheel --outdir /dist


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="ccc-contextcompiler" \
      org.opencontainers.image.description="Generate structured, LLM-optimized context from codebases" \
      org.opencontainers.image.source="https://github.com/benneberg/contextcompiler" \
      org.opencontainers.image.licenses="MIT"

# Non-root user — UID/GID 1000 matches most CI runners
RUN addgroup --system --gid 1000 ccc \
 && adduser  --system --uid 1000 --ingroup ccc --no-create-home ccc

WORKDIR /workspace

# Install the wheel with all optional extras
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl[all] \
 && rm /tmp/*.whl \
 # Smoke-test the CLI is importable
 && ccc --version

# Drop to non-root before CMD
USER ccc

# Mount the repo you want to analyse at /workspace
VOLUME ["/workspace"]

ENTRYPOINT ["ccc"]
CMD ["--help"]
