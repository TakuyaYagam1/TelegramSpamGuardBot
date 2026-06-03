# syntax=docker/dockerfile:1.24.0

FROM python:3.14.5-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_VERSION=26.1.2

WORKDIR /app

RUN groupadd --system app && \
    useradd --system --gid app --home-dir /app app

COPY pyproject.toml README.md requirements.lock ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade "pip==${PIP_VERSION}" && \
    python -m pip install -c requirements.lock .

RUN mkdir -p /app/logs && \
    chown -R app:app /app

USER app

CMD ["python", "-m", "app"]
