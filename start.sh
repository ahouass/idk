#!/bin/bash

echo "=========================================="
echo "🚀 Starting TFG SOA Microservices System"
echo "=========================================="

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detect Python command (python or python3)
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ Python is not installed. Please install Python 3.8+ first."
    echo "   Download from: https://www.python.org/downloads/"
    exit 1
fi

echo "Using Python: $PYTHON_CMD"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt --quiet
fi

# Initialize database
echo "🗄️ Initializing database..."
python init_db.py

# Create uploads directory
mkdir -p uploads

# Kill any existing processes on the ports
echo "Cleaning up existing processes..."
for port in 5000 5001 5002 5003 5004 5005; do
    pid=$(netstat -ano 2>/dev/null | grep ":$port " | awk '{print $5}' | head -1)
    if [ ! -z "$pid" ] && [ "$pid" != "0" ]; then
        taskkill //F //PID $pid 2>/dev/null
    fi
done
sleep 2

# Start services in background
echo ""
echo "Starting microservices..."

cd "$SCRIPT_DIR/services/auth" && python app.py &
sleep 1
echo "✅ Auth service started on port 5001"

cd "$SCRIPT_DIR/services/users" && python app.py &
sleep 1
echo "✅ Users service started on port 5002"

cd "$SCRIPT_DIR/services/files" && python app.py &
sleep 1
echo "✅ Files service started on port 5003"

cd "$SCRIPT_DIR/services/appointments" && python app.py &
sleep 1
echo "✅ Appointments service started on port 5004"

cd "$SCRIPT_DIR/services/notifications" && python app.py &
sleep 1
echo "✅ Notifications service started on port 5005"

cd "$SCRIPT_DIR/services/gateway" && python app.py &
sleep 2
echo "✅ Gateway (ESB) started on port 5000"

echo ""
echo "=========================================="
echo "🎉 All services started successfully!"
echo "=========================================="
echo ""
echo "📍 Access the system:"
echo "   Frontend: http://localhost:5000"
echo "   API Docs: http://localhost:5000/docs"
echo ""
echo "📊 Default users:"
echo "   Tutor:     tutor1 / tutor123"
echo "   Student:   estudiante1 / estudiante123"
echo ""
echo "Press Ctrl+C to stop all services"
echo "=========================================="

wait