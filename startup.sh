#!/bin/bash
set -e

echo "Installing dependencies..."
pip3 install -r requirements.txt
pip3 install peft==0.15.2
echo "Installing sentence-transformers ..."
pip3 install sentence-transformers==4.1.0

echo "Starting app..."
uvicorn api:app --host 0.0.0.0 --port 8080
