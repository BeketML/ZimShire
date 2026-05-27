FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x scripts/start_api.sh

# Default: API server (overridden to mcp command in docker-compose for the mcp service)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
