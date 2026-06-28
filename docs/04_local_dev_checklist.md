# Phase 0 — Step 4: Local Dev Checklist & Environment Setup

> **Goal**: Verify all services are connected before writing any application code.
> **Time estimate**: 15–20 minutes

---

## What You Should Have by Now

After completing steps 1–3, you should have:

### From Azure AI Foundry (Step 1)
```
AZURE_OPENAI_ENDPOINT=https://<hub>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_API_VERSION=2025-03-01-preview
THINK_MODEL_DEPLOYMENT=gpt-5.4
SOLVE_MODEL_DEPLOYMENT=gpt-5.4-mini
NANO_MODEL_DEPLOYMENT=gpt-5.4-nano
HUGGINGFACE_IMAGE_MODEL=black-forest-labs/FLUX.1-dev
SPEECH_VOICE_NAME=en-US-JennyNeural
COMPACTION_MODEL_DEPLOYMENT=o4-mini
```

### From Azure Services, Groq, & Hugging Face (Step 2)
```
GROQ_API_KEY=<your-groq-key>, 
HUGGINGFACE_API_KEYS=hf_key1,hf_key2,hf_key3,hf_key4,hf_key5,hf_key6
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://agent-ochuko-docintelligence.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<key>
AZURE_VISION_ENDPOINT=https://agent-ochuko-vision.cognitiveservices.azure.com/
AZURE_VISION_KEY=<key>
AZURE_SPEECH_KEY=<key>
AZURE_SPEECH_REGION=southafricanorth
AZURE_STORAGE_ACCOUNT_NAME=agentochukostore
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_APP_CONFIG_CONNECTION_STRING=Endpoint=https://agent-ochuko-appconfig...
```

### From Supabase (Step 3)
```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=<jwt secret>
```

### From Google Cloud Console (Step 3)
```
GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-<secret>
```

---

## Create Your Local `.env` File

> [!CAUTION]
> This file must NEVER be committed to Git. Make sure `.env` is in your `.gitignore`.

Create this file at `agent-ochuko/backend/.env` (we'll create the folder in Phase 1):

```env
# ==============================
# Azure OpenAI (Responses API)
# ==============================
AZURE_OPENAI_ENDPOINT=https://<hub>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your key>
AZURE_OPENAI_API_VERSION=2025-03-01-preview
THINK_MODEL_DEPLOYMENT=gpt-5.4
SOLVE_MODEL_DEPLOYMENT=gpt-5.4-mini
NANO_MODEL_DEPLOYMENT=gpt-5.4-nano
HUGGINGFACE_IMAGE_MODEL=black-forest-labs/FLUX.1-dev
SPEECH_VOICE_NAME=en-US-JennyNeural
COMPACTION_MODEL_DEPLOYMENT=o4-mini

# ==============================
# Azure Speech (REST API)
# ==============================
AZURE_SPEECH_KEY=<your key>
AZURE_SPEECH_REGION=southafricanorth

# ==============================
# Groq (Speech-to-Text) & Hugging Face (Image Gen)
# ==============================
GROQ_API_KEY=gsk_...
HUGGINGFACE_API_KEYS=hf_key1,hf_key2,hf_key3,hf_key4,hf_key5,hf_key6

# ==============================
# Azure Document Intelligence (OCR)
# ==============================
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://agent-ochuko-docintelligence.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<your key>

# ==============================
# Azure Computer Vision
# ==============================
AZURE_VISION_ENDPOINT=https://agent-ochuko-vision.cognitiveservices.azure.com/
AZURE_VISION_KEY=<your key>

# ==============================
# Azure Blob Storage
# ==============================
AZURE_STORAGE_ACCOUNT_NAME=agentochukostore
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...

# ==============================
# Azure App Configuration
# ==============================
AZURE_APP_CONFIG_CONNECTION_STRING=Endpoint=https://agent-ochuko-appconfig...

# ==============================
# Supabase
# ==============================
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_JWT_SECRET=<jwt secret>

# ==============================
# Environment
# ==============================
ENVIRONMENT=development
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## Verify Each Service (Quick Smoke Tests)

Before writing the app, verify each Azure service is working. You can do this from the **Azure portal** itself:

### Test Azure OpenAI
1. Azure portal → Azure OpenAI resource → **"Go to Azure OpenAI Studio"**
   (or use AI Foundry playground as you did in Step 1)
2. Send a test message — confirm response

### Test Document Intelligence
1. Azure portal → your Document Intelligence resource → **"Try it out"** 
2. Upload a simple PDF → confirm it returns text

### Test Computer Vision
1. Azure portal → your Computer Vision resource → **"Try it out"**
2. Upload an image → confirm it returns description

### Test Speech (Groq & Azure OpenAI TTS)
1. Use your Groq API Key to test Whisper Large v3 Turbo in Python or via raw API (e.g. standard curl/httpx request).
2. Test Azure OpenAI TTS by opening your TTS model deployment in AI Foundry playground and typing text to generate speech.

### Test Supabase Auth
1. Supabase dashboard → **Authentication** → **"Providers"** → Google → confirm it shows as enabled
2. Your SQL tables should be visible under **Table Editor**

---

## Software to Install on Your Machine

Before Phase 1 coding begins, make sure you have:

```bash
# Check these are installed:
node --version      # Should be 18+ 
python --version    # Should be 3.11+
docker --version    # Docker Desktop for Windows
git --version

# Install if missing:
# Node.js: https://nodejs.org (LTS version)
# Python: https://python.org (3.11+)
# Docker Desktop: https://docker.com/products/docker-desktop
# Git: should already be installed
```

### VS Code Extensions (if you use VS Code)
- Python
- Docker
- REST Client (for testing API endpoints)
- Supabase (optional)
- Tailwind CSS IntelliSense

---

## Project Folder Setup

When ready to start Phase 1, you'll create:

```
c:\Users\T14 GEN 5\Documents\WORK AND PLAN\AZURE SYSTEM-AUTH AT SCALE\
├── docs\                   ← you are here (these guides)
├── agent-ochuko\           ← main project (created in Phase 1)
│   ├── frontend\
│   ├── admin\
│   ├── backend\
│   ├── functions\
│   ├── infra\
│   └── docker-compose.yml
└── credentials.txt         ← OPTIONAL local reference (never commit this)
```

---

## Phase 0 — Complete Checklist

Go through this before telling me you're ready to code:

### Azure AI Foundry
- [ ] Hub created in South Africa North
- [ ] Project created
- [ ] All 5 model deployments working: `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `tts-1-ochuko`, `o4-mini` (tested in playground)
- [ ] Endpoint + API Key saved

### Azure Services, Groq, & Hugging Face
- [ ] Document Intelligence created + tested
- [ ] Computer Vision created + tested  
- [ ] Speech Services created (F0 free tier) + tested
- [ ] Groq API Key obtained from Groq Console and tested
- [ ] Comma-separated list of 5–6 Hugging Face API keys obtained and tested
- [ ] Blob Storage created with 3 containers
- [ ] App Configuration created with all keys (including `HUGGINGFACE_IMAGE_MODEL` and `SPEECH_VOICE_NAME`)
- [ ] Key Vault created with all secrets (including `AZURE-SPEECH-KEY`, `AZURE-SPEECH-REGION`, `GROQ-API-KEY`, and `HUGGINGFACE-API-KEYS`)
- [ ] Container Apps environment created with Managed Identity
- [ ] Function App created with Managed Identity + Key Vault access

### Supabase
- [ ] Project created (Cape Town region)
- [ ] All 3 SQL migrations run
- [ ] RLS enabled + policies applied
- [ ] Google OAuth working
- [ ] Your account is `superadmin`
- [ ] Realtime enabled for messages + conversations
- [ ] Storage buckets created

### Local Machine
- [ ] Node 18+ installed
- [ ] Python 3.11+ installed
- [ ] Docker Desktop installed
- [ ] `.env` file ready (not committed to git)

---

## 🚀 When You're Done

Come back and say **"Phase 0 complete"** and tell me:
1. Did everything work in South Africa North or did you need another region?
2. What models are available on your deployment?
3. Any quota limits you noticed?

Then we start Phase 1: writing the FastAPI backend + React frontend + streaming chat.
