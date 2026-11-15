FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt \
    && groupadd --gid 10001 iku-auth \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin iku-auth
COPY app ./app
COPY entrypoint.sh ./entrypoint.sh
RUN chmod 0555 ./entrypoint.sh
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
