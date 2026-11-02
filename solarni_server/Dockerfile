ARG BUILD_FROM
FROM ${BUILD_FROM}

# iproute2: popis mrežnih kartica (ip -j addr); tzdata: lokalno vrijeme (dani, izvještaji); jpeg/zlib: Pillow
RUN apk add --no-cache iproute2 tzdata jpeg zlib libwebp
COPY requirements.txt /tmp/requirements.txt
RUN apk add --no-cache --virtual .build build-base jpeg-dev zlib-dev libwebp-dev \
    && pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && apk del .build

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
CMD ["/run.sh"]
