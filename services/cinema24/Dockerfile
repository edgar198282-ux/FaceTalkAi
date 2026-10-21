FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data/cinema24
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates gosu && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY core.py prepare.py server.py ./
COPY entrypoint.sh ./
RUN useradd -r -u 10001 cinema && chmod +x /srv/entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["/srv/entrypoint.sh"]
