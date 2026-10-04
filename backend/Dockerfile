# backend/Dockerfile

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# Usar HTTPS para los repos de Debian: el firewall (FortiGate) bloquea apt por HTTP
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get dist-upgrade -y && apt-get install -y --no-install-recommends \
    binutils \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    geos-bin \
    proj-bin \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]