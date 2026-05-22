FROM python:3.12-slim

WORKDIR /app

COPY api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY orchestrator/logger.py orchestrator/metrics.py orchestrator/orchestrator.py ./
COPY api/main.py ./

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
