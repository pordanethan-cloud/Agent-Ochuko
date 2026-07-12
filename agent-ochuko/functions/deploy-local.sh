#!/bin/bash
# Local deployment script for Azure Functions
# Usage: ./deploy-local.sh

set -e

echo "=== Starting local Azure Functions deployment ==="

# Navigate to functions directory
cd "$(dirname "$0")"

# Install dependencies locally
echo "Step 1: Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt --target .python_packages/lib/site-packages

# Publish to Azure Functions
echo "Step 2: Publishing to Azure Functions..."
func azure functionapp publish agent-ochuko-functions \
  --python \
  --build local

echo "=== Deployment complete ==="
