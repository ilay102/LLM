FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Presidio needs a spaCy English model
RUN python -m spacy download en_core_web_sm

COPY . .

# Persistent data directory for SQLite (tenants + events)
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
