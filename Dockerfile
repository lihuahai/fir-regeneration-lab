FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    PORT=10000 \
    FIR_STATIC_DIR=/app/site
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY site ./site
COPY analysis/engine.py analysis/web.py analysis/example.json ./analysis/
COPY gunicorn.conf.py ./
RUN useradd --create-home --uid 10001 fir
USER fir
EXPOSE 10000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "--chdir", "analysis", "web:app"]
