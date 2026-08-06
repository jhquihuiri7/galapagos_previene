# Imágenes de producción de Galápagos Previene.
#
# Un mismo Dockerfile produce dos imágenes distintas mediante `target`:
#
#   bot  Cliente de Telegram por polling. No abre puertos.
#   api  Servicio REST de solo lectura que consume SIGTAR.
#
# Se separan porque sus dependencias y su exposición no coinciden: el bot no
# debe cargar un servidor HTTP que no usa, y la API no necesita la librería de
# Telegram completa. Ambas comparten la etapa `base` para reutilizar caché.

FROM python:3.11-slim AS base

# PYTHONUNBUFFERED mantiene los logs visibles en `docker compose logs` sin
# esperar a que se llene el búfer. PYTHONDONTWRITEBYTECODE evita generar
# __pycache__ dentro del contenedor, que además sería de solo lectura.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario sin privilegios. El UID fijo facilita auditar el proceso desde el
# host y evita que el contenedor corra como root.
RUN useradd --system --uid 10001 --no-create-home galapagos


# ---------------------------------------------------------------- bot --------
FROM base AS bot

# Las dependencias se copian primero y en una capa aparte: mientras
# requirements.txt no cambie, Docker reutiliza la caché al reconstruir el
# código. Se instala solo el archivo de producción, sin pytest.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Únicamente lo que el bot necesita en tiempo de ejecución. El resto (tests,
# docs, README) queda fuera gracias a .dockerignore.
COPY main.py schema.sql ./
COPY app ./app

RUN chown -R galapagos:galapagos /app
USER galapagos

CMD ["python", "main.py"]


# ---------------------------------------------------------------- api --------
FROM base AS api

COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

# La API no ejecuta schema.sql —su rol de PostgreSQL no tiene permisos de DDL—
# así que el archivo no se copia. Tampoco se copia main.py: es el bot.
COPY app ./app

RUN chown -R galapagos:galapagos /app
USER galapagos

EXPOSE 8080

# Un solo worker: el trabajo es de entrada/salida y asyncio lo cubre sin
# multiplicar procesos ni pools de PostgreSQL. Si hiciera falta escalar, es
# preferible levantar más réplicas del contenedor.
CMD ["uvicorn", "app.api.main:build_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", "--no-server-header", \
     "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
