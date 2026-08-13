FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copy error codes data into the container
COPY data/ ./data/

EXPOSE 8002

CMD ["uvicorn", "server:http_app", "--host", "0.0.0.0", "--port", "8002"]
