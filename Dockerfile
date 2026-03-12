# Lightweight Dockerfile for Raspberry Pi 1 (arm6vl)
FROM arm32v6/alpine:latest

# Set working directory
WORKDIR /app

# Install only necessary system dependencies (keep minimal)
RUN apk add --no-cache python3 py3-pip gcc python3-dev musl-dev

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application code
COPY src/ src/

# Run the application
CMD ["python3", "src/main.py", "--config", "config.yaml"]
