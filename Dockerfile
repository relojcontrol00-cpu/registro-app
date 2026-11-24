FROM python:3.12-slim

# El servidor es stdlib-only: no hay pip install ni build step.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8050 \
    OPEN_BROWSER=0 \
    DB_FILE=/app/data/Registro_Medidores_Espacio_OX.sqlite

WORKDIR /app

COPY servidor_visualizador.py index.html ./
# Semilla de la base de datos (fallback si se corre la imagen sin montaje).
# Con docker-compose.yml este archivo queda tapado por el bind mount :ro de Windows.
COPY Registro_Medidores_Espacio_OX.sqlite /app/data/Registro_Medidores_Espacio_OX.sqlite

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/api/kpis', timeout=2)"

CMD ["python", "servidor_visualizador.py"]
