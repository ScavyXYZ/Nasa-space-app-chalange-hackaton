FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000
COPY requirements.txt requirements-data.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY algorithms ./algorithms
COPY backend ./backend
COPY scripts ./scripts
COPY science ./science
COPY data/processed ./data/processed
COPY data/runtime_manifest.json ./data/runtime_manifest.json
RUN python scripts/prepare_runtime_data.py
COPY frontend/gis-check ./frontend/gis-check
COPY --from=frontend /build/dist ./frontend/dist
RUN useradd --create-home explorer && chown -R explorer:explorer /app
USER explorer
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=4)" || exit 1
CMD ["sh","-c","exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
