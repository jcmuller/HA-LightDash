ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip

COPY requirements.txt /
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

COPY app /app
COPY run.sh /

RUN chmod a+x /run.sh

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

WORKDIR /app
CMD ["/run.sh"]