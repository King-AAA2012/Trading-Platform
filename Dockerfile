# CasuallyHedge web app (public beta). Works on any container host: Render, Koyeb, Fly.io, Hugging Face Spaces, a VPS...
#   docker build -t casuallyhedge .
#   docker run -p 8420:8420 -e DATABASE_URL=postgresql://... casuallyhedge
# The local AI (Ollama) isn't included; AI features fall back to rule-based text without it.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8420 CH_BETA=1 COOKIE_SECURE=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home app && mkdir -p data && chown -R app /app
USER app
EXPOSE 8420
CMD ["sh", "-c", "python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
