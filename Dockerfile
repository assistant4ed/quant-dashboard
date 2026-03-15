FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHON_BIN=/usr/local/bin/python
ENV PORT=8080

EXPOSE ${PORT}

CMD gunicorn "app:create_app()" --bind "0.0.0.0:${PORT}" --workers 2 --timeout 120
