FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips-dev \
    libvips-tools \
    poppler-utils \
    libpoppler-dev \
    librsvg2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 3001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3001"]
