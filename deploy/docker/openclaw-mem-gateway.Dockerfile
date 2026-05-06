# openclaw-mem-gateway sidecar image.
# Production builds should pin PYTHON_IMAGE by digest in the build pipeline.
ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    OPENCLAW_MEM_GATEWAY_HOST=127.0.0.1 \
    OPENCLAW_MEM_GATEWAY_PORT=8765 \
    OPENCLAW_MEM_GATEWAY_MAX_BODY_BYTES=131072 \
    OPENCLAW_MEM_GATEWAY_EXPORT_ROOT=/exports

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin openclaw-mem \
    && mkdir -p /app /data /workspace /exports /var/log/openclaw-mem \
    && chown -R openclaw-mem:openclaw-mem /app /data /exports /var/log/openclaw-mem

WORKDIR /app
COPY --chown=openclaw-mem:openclaw-mem . /app
RUN python -m pip install --no-cache-dir --upgrade pip uv \
    && uv pip install --system --no-cache .

USER openclaw-mem
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import json, urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=2); assert json.loads(r.read().decode()).get('ok') is True"

CMD ["openclaw-mem-gateway", "--host", "0.0.0.0", "--port", "8765", "--audit-log", "/var/log/openclaw-mem/gateway-audit.jsonl", "--export-root", "/exports"]
