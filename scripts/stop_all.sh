#!/bin/bash
# Stop semua service yang distart oleh start_all.sh
for service in dashboard chatbot vllm; do
    PID_FILE=".pids/$service.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill "$PID" 2>/dev/null; then
            echo "Stopped $service (PID $PID)"
        else
            echo "WARNING: $service (PID $PID) already stopped"
        fi
        rm "$PID_FILE"
    else
        echo "No PID file for $service — already stopped or never started"
    fi
done
