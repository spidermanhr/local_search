#!/bin/bash
cd "$(dirname "$0")"
python3 server.py &
sleep 2
xdg-open http://127.0.0.1:5000
