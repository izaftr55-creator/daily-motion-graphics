FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip ffmpeg chromium fonts-liberation fonts-noto-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY animation-kit /app/animation-kit

RUN cd /app/animation-kit/kit \
    && npm install --omit=dev --no-audit --no-fund \
    && npm install -g hyperframes@0.8.34

COPY topics.json server.py /app/

ENV HYPERFRAMES_BROWSER_PATH=/usr/bin/chromium
ENV PRODUCER_EXPERIMENTAL_FAST_CAPTURE=false
ENV DATA_DIR=/data

EXPOSE 8080
CMD ["python3", "/app/server.py"]
