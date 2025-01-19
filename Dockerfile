FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

RUN pip install poetry uvicorn
COPY pyproject.toml poetry.lock* /app/
RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY . /app

# Set environment variables
ENV PYTHONPATH=/app

# Expose the web server port
EXPOSE 8081
