FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY app/__init__.py app/__init__.py
RUN pip install .

COPY . .
RUN pip install --no-deps . && useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "./docker-entrypoint.sh"]
