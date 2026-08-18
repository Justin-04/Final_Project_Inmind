FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed by torch/transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/agent-system-a/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/agent-system-a/ .

# Copy BERT intent classifier model
COPY models/bert_intent_classifier/model/ /app/models/bert_intent_classifier/model/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
