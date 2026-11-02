ARG BUILD_FROM
FROM ${BUILD_FROM}

# iproute2: popis mrežnih kartica (ip -j addr); tzdata: lokalno vrijeme (dani, izvještaji); jpeg/zlib: Pillow
RUN apk add --no-cache iproute2 tzdata jpeg zlib libwebp curl
COPY requirements.txt /tmp/requirements.txt
RUN apk add --no-cache --virtual .build build-base jpeg-dev zlib-dev libwebp-dev \
    && pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
# zdravlje: /api/v1/ping vraća 503 kad nit pollera ne radi → Supervisor ponovno pokrene add-on
HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3     CMD sh -c 'curl -fsS "http://127.0.0.1:$(cat /tmp/solari_port 2>/dev/null || echo 8700)/api/v1/ping" >/dev/null || exit 1'
CMD ["/run.sh"]
