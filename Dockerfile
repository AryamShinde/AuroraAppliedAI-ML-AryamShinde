# Minimal Dockerfile for container-based deployment (Render / other platforms)
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code only (no local .env)
COPY qa_app.py ./

# Expose runtime port (Render sets $PORT; fallback 8000 locally)
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "qa_app:app", "--host", "0.0.0.0", "--port", "8000"]
