#!/bin/bash

echo "=========================================="
echo "🚀 Starting TFG SOA Microservices System"
echo "=========================================="

# Create required directories
# mkdir -p data uploads

# Kill any existing processes on the ports
echo "Cleaning up existing processes..."
fuser -k 5000/tcp 2>/dev/null
fuser -k 5001/tcp 2>/dev/null
fuser -k 5002/tcp 2>/dev/null
fuser -k 5003/tcp 2>/dev/null
fuser -k 5004/tcp 2>/dev/null
fuser -k 5005/tcp 2>/dev/null
sleep 2

# Start services in background
echo ""
echo "Starting microservices..."

cd /home/aiman/idk/services/auth && python3 app.py &
sleep 1
echo "✅ Auth service started on port 5001"

cd /home/aiman/idk/services/users && python3 app.py &
sleep 1
echo "✅ Users service started on port 5002"

cd /home/aiman/idk/services/files && python3 app.py &
sleep 1
echo "✅ Files service started on port 5003"

cd /home/aiman/idk/services/appointments && python3 app.py &
sleep 1
echo "✅ Appointments service started on port 5004"

cd /home/aiman/idk/services/notifications && python3 app.py &
sleep 1
echo "✅ Notifications service started on port 5005"

cd /home/aiman/idk/services/gateway && python3 app.py &
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