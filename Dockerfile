# Сборка: протоколы PDF -> site/data.js
FROM python:3.12-slim AS data
RUN pip install --no-cache-dir pymupdf
WORKDIR /app
COPY tools ./tools
COPY protocols ./protocols
RUN mkdir site && python tools/parse_protocols.py

# Раздача статики
FROM nginx:1.29-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY site/index.html site/app.js site/style.css /usr/share/nginx/html/
COPY --from=data /app/site/data.js /usr/share/nginx/html/data.js
COPY --from=data /app/site/protocols /usr/share/nginx/html/protocols
