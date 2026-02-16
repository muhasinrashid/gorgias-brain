#!/bin/bash

# Function to kill background processes on exit
cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID
    kill $FRONTEND_PID
    exit
}

trap cleanup SIGINT

echo "🚀 Initializing Universal Support Brain..."

# 1. Start Docker Infrastructure
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running."
    exit 1
fi
echo "📦 Starting Database and Redis..."
docker-compose up -d

# 2. Setup Backend
echo "🐍 Setting up Backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1

# Check for .env
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: backend/.env not found. Copying .env.example..."
    cp .env.example .env
    echo "❗ PLEASE EDIT backend/.env with your real API keys!"
fi

# Start Backend in background
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "✅ Backend running at http://localhost:8000"

# 3. Setup Frontend
echo "⚛️  Setting up Frontend..."
cd ../frontend
npm install > /dev/null 2>&1
# Start Frontend in background
npm run dev &
FRONTEND_PID=$!
echo "✅ Frontend running at http://localhost:3000"

echo "------------------------------------------------"
echo "🎉 Application is live!"
echo "➡️  API Docs (Swagger): http://localhost:8000/docs"
echo "➡️  Sidebar Interface:   http://localhost:3000/sidebar"
echo "------------------------------------------------"
echo "Press Ctrl+C to stop."

wait
