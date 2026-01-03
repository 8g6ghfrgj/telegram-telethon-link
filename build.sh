#!/bin/bash
# build.sh - Build script for Render.com

echo "🔧 Starting build process..."

# Update pip
python -m pip install --upgrade pip

# Install wheel first
pip install wheel

# Install dependencies with specific versions to avoid conflicts
pip install \
  python-telegram-bot==20.7 \
  Telethon==1.34.0 \
  aiosqlite==0.19.0 \
  aiofiles==23.2.1 \
  cryptography==42.0.5 \
  psutil==5.9.8 \
  fastapi==0.104.1 \
  uvicorn==0.24.0 \
  httpx==0.25.2 \
  pytz==2023.3

# Verify installations
echo "📦 Verifying installations..."
pip list | grep -E "(telegram|telethon|aiosqlite|aiofiles|cryptography|psutil|fastapi|uvicorn|httpx|pytz)"

# Create necessary directories
mkdir -p backups cache_data exports logs

echo "✅ Build completed successfully!"
