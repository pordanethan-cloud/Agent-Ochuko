#!/bin/bash
set -e

# Resolve script directory path
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Redirect stdout and stderr to deploy_local.log while still showing it on terminal
exec > >(tee -a "$SCRIPT_DIR/deploy_local.log") 2>&1

echo "Starting local build and deploy..."

# Resolve paths
WORKSPACE_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
BACKEND_DIR="$SCRIPT_DIR/../../backend"

# 1. Build the Docker image
echo "Building Docker image..."
docker build -t ochair1/agent-ochuko-api:latest -f "$BACKEND_DIR/Dockerfile" "$WORKSPACE_ROOT"

# 2. Push to Docker Hub
echo "Pushing image to Docker Hub..."
docker push ochair1/agent-ochuko-api:latest

# 3. Read Google API Keys from backend/.env and update Azure Container App
echo "Deploying to Azure Container App..."
ENV_FILE="$BACKEND_DIR/.env"
ENV_VARS=""
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # Ignore comments and empty lines
        if [[ ! "$line" =~ ^# ]] && [[ "$line" == *"="* ]]; then
            key=$(echo "$line" | cut -d'=' -f1 | tr -d '[:space:]')
            val=$(echo "$line" | cut -d'=' -f2- | tr -d '[:space:]')
            if [[ "$key" == "GOOGLE_API_KEY" || "$key" == "GEMINI_API_KEY" || "$key" == "GEMINI_API_KEY_2" || "$key" == "GEMINI_API_KEY_3" || "$key" == "GEMINI_API_KEY_4" ]]; then
                ENV_VARS="$ENV_VARS $key=$val"
            fi
        fi
    done < "$ENV_FILE"
fi

if [ -n "$ENV_VARS" ]; then
    echo "Updating container app with Google API keys..."
    az containerapp update --name agent-ochuko-api --resource-group rg-ochuko --image ochair1/agent-ochuko-api:latest --set-env-vars $ENV_VARS
else
    az containerapp update --name agent-ochuko-api --resource-group rg-ochuko --image ochair1/agent-ochuko-api:latest
fi

echo "Deployment completed successfully!"
