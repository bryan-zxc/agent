FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python package management
RUN pip install uv

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Copy source code needed for local package build
COPY src/ src/
COPY README.md ./

# Install Python dependencies (including local package)
RUN uv sync --frozen

# Copy remaining application files
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Set Python path
ENV PYTHONPATH=/app/src

# Expose ports
EXPOSE 8000 8888

# Run the application
CMD ["uv", "run", "python", "main.py"]