FROM node:20-alpine

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Create shared types directory if it doesn't exist
RUN mkdir -p shared

# Expose port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev"]