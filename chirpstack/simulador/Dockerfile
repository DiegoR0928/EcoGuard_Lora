FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED 1
WORKDIR /app

RUN pip install --no-cache-dir cryptography==45.*

COPY simulador.py /app/

EXPOSE 8070

CMD ["python", "simulador.py"]
