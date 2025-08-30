FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Chrome for Selenium
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    curl \
    wget \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome (cross-platform)
RUN apt-get update \
    && if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
        && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
        && apt-get update \
        && apt-get install -y google-chrome-stable; \
    else \
        apt-get install -y chromium chromium-driver; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver for amd64, chromium-driver is already installed for arm64
RUN if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        CHROMEDRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE) \
        && wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/${CHROMEDRIVER_VERSION}/chromedriver_linux64.zip" \
        && unzip /tmp/chromedriver.zip -d /tmp/ \
        && mv /tmp/chromedriver /usr/local/bin/chromedriver \
        && chmod +x /usr/local/bin/chromedriver \
        && rm /tmp/chromedriver.zip; \
    fi

# Install Node.js 20 LTS for MCP servers
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g npm@latest \
    && rm -rf /var/lib/apt/lists/*

# Verify Node.js installations
RUN node --version && npm --version && npx --version

# Install uv for fast Python package management
RUN pip install uv

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Copy source code needed for local package build
COPY src/ src/
COPY README.md ./

# Install Python dependencies (including local package)
RUN uv sync --frozen

# Copy package.json first for better caching
COPY package.json* ./

# Install MCP servers globally during build
# Direct global installation ensures they're available in the container
RUN if [ -f package.json ]; then \
    npm install -g @modelcontextprotocol/server-github @modelcontextprotocol/server-filesystem; \
    fi

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