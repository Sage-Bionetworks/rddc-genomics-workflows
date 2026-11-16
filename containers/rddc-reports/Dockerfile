# rddc-reports: the Python code of the report-findings pipeline.
# Build from the repo root:  make image   (the `runtime` stage; `test` adds pytest)
# Modules pin this image by version tag; bump `version` in pyproject.toml and the tag together.

FROM python:3.12.8-slim-bookworm AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.12.8-slim-bookworm AS runtime
# libpq5: runtime library of psycopg2, which hgvs imports even though the pipeline never connects
# to Postgres. procps: `ps`, which Nextflow uses for task metrics.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 procps \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels rddc-reports \
 && rm -rf /wheels
# hgvs reads this at import; keep it from looking for a UTA database or SeqRepo by default.
ENV HGVS_SEQREPO_DIR="" \
    PYTHONDONTWRITEBYTECODE=1
LABEL org.opencontainers.image.source="https://github.com/Sage-Bionetworks/rddc-genomics-workflows" \
      org.opencontainers.image.description="RDDC report-findings: report extraction, HGVS validation, VRS"
ENTRYPOINT []
CMD ["rddc-reports", "--help"]

# Test image: the runtime plus pytest. CI runs the suite with --network none and the repo
# mounted at /repo:  make py-test
FROM runtime AS test
RUN pip install --no-cache-dir pytest==8.3.4
WORKDIR /repo/containers/rddc-reports
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
