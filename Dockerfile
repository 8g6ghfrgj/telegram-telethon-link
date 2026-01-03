FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
COPY constraints.txt .

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p backups cache_data exports logs

# Run the application
CMD ["python", "bot.py"]
