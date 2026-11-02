ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apk add --no-cache tzdata curl
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh
WORKDIR /app
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3     CMD curl -fsS http://127.0.0.1:8099/ >/dev/null || exit 1
CMD ["/run.sh"]
