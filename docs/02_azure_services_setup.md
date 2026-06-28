# Phase 0 — Step 2: Azure Services Setup

> **Goal**: Create all the Azure supporting services (OCR, Vision, Speech, Blob Storage, App Configuration, Key Vault, Container Apps, Functions).
> **Time estimate**: 45–60 minutes
> **Where**: [https://portal.azure.com](https://portal.azure.com)

---

## Overview — What You're Creating

| Service | Azure Name | Purpose |
|---|---|---|
| Azure Document Intelligence | `agent-ochuko-docintelligence` | OCR — read PDFs and documents |
| Azure Computer Vision | `agent-ochuko-vision` | Analyze images uploaded by users |
| Azure Speech Services | `agent-ochuko-speech` | Voice-to-text + text-to-voice |
| Azure Blob Storage | `agentochukostore` | Store uploaded files + AI-generated files |
| Azure App Configuration | `agent-ochuko-appconfig` | Store model names + feature flags (no redeploy needed) |
| Azure Key Vault | `agent-ochuko-kv` | Store all secrets securely |
| Azure Container Apps | `agent-ochuko-aca` | Host your FastAPI backend |
| Azure Functions | `agent-ochuko-functions` | Background jobs (cron, quota reset, etc.) |

> [!NOTE]
> Use the **same resource group** for everything: `rg-ochuko` (created in Step 1)

---

## Service 1 — Azure Document Intelligence (OCR)

1. In Azure portal, click **"+ Create a resource"**
2. Search for **"Document Intelligence"** → click it → **Create**
3. Fill in:
   - **Subscription**: your student subscription
   - **Resource group**: `rg-ochuko`
   - **Region**: `South Africa North` (if unavailable, use `West Europe`)
   - **Name**: `agent-ochuko-docintelligence`
   - **Pricing tier**: `Free (F0)` — 500 pages/month, perfect for student use
4. Click **Review + Create** → **Create**

**Collect credentials** (after deployment):
- Go to resource → **"Keys and Endpoint"**
```
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://agent-ochuko-docintelligence.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=<your-document-intelligence-key>
```

---

## Service 2 — Azure Computer Vision

1. **"+ Create a resource"** → search **"Computer Vision"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Region**: `South Africa North`
   - **Name**: `agent-ochuko-vision`
   - **Pricing tier**: `Free (F0)` — 5,000 transactions/month
3. **Review + Create** → **Create**

**Collect credentials**:
```
AZURE_VISION_ENDPOINT=https://agent-ochuko-vision.cognitiveservices.azure.com/
AZURE_VISION_KEY=<your-vision-key>
```

---

## Service 3 — Azure Speech Services (Text-to-Speech)

> Allows converting chat assistant text into high-quality human-like neural voice. We'll use the **Free (F0) tier** which provides **500,000 free characters per month**.
> 
> *   **Speech-to-Text (STT)**: Handled by **Groq (Whisper Large v3 Turbo)** via a lightweight REST API for speed and zero lag.
> *   **Text-to-Speech (TTS)**: Handled by **Azure Cognitive Speech Services**. To prevent Docker container bloat, we call Azure's lightweight **REST API** directly instead of using the heavy C++ Azure Speech SDK.
> *   **Fallback mechanism (On-device Google/Web Speech)**: If Azure is offline, or if the user exhausts the 500,000 monthly free characters, the React frontend instantly falls back to playing the text via the browser's built-in `window.speechSynthesis` (which uses Google/local device speech engine for free).

1. In the Azure portal, click **"+ Create a resource"**
2. Search for **"Speech"** → click **Create**
3. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Region**: `South Africa North` (or `West Europe` if South Africa has F0 quota limits)
   - **Name**: `agent-ochuko-speech`
   - **Pricing tier**: `Free F0` (500k characters/month free)
4. Click **Review + Create** → **Create**

**Collect credentials**:
- Go to your speech resource → **"Keys and Endpoint"**
```
AZURE_SPEECH_KEY=<your-speech-key>
AZURE_SPEECH_REGION=southafricanorth
```


---

## Service 4 — Azure Blob Storage

> Used to store uploaded files (PDFs, images) and generated files (DOCX, XLSX, PDF).

1. **"+ Create a resource"** → search **"Storage account"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Storage account name**: `agentochukostore` (must be globally unique, lowercase, no dashes)
   - **Region**: `South Africa North`
   - **Performance**: `Standard`
   - **Redundancy**: `Locally-redundant storage (LRS)` — cheapest option
3. **Review + Create** → **Create**

**After creation — create containers**:
1. Go to resource → **"Containers"** (in the left menu under Data storage)
2. Create these containers:
   - `uploads` — for user-uploaded files (PDFs, images)
   - `generated` — for AI-generated files (DOCX, XLSX, PDF)
   - `exports` — for exported conversation JSON files
3. For each container, set **"Public access level"** to `Private`

**Collect credentials**:
```
AZURE_STORAGE_ACCOUNT_NAME=agentochukostore
AZURE_STORAGE_CONNECTION_STRING=<your-storage-connection-string>
```
> Get the connection string: Storage account → **"Access keys"** → copy "Connection string"

---

## Service 4b — Azure Queue Storage (Agent Job Message Bus)

> This is the decoupling layer. When a user submits an OCR, Vision, Speech, File Gen, or Image Gen request, FastAPI writes a job message here. Azure Functions pick it up automatically — no polling, no Redis, no RabbitMQ.

Good news: **Azure Queue Storage is part of the same Storage Account** you just created. You don’t need a new resource — just create a queue inside it.

1. Go to your storage account (`agentochukostore`) in the portal
2. In the left menu under **"Data storage"**, click **"Queues"**
3. Click **"+ Queue"**
4. Name it: `agent-jobs`
5. Click **OK**

Also create a dead-letter queue for failed jobs:
- Name: `agent-jobs-poison`
(Azure Queue Storage automatically routes messages that fail 5 times to the `-poison` queue)

**Collect credentials** (same connection string as Blob Storage — no separate key needed):
```
AZURE_QUEUE_STORAGE_CONNECTION_STRING=<same connection string as blob storage>
AZURE_QUEUE_NAME=agent-jobs
```

> [!NOTE]
> One storage account, one connection string, both Blob containers and Queues accessible. This is intentional — minimum secret surface.

---

## Service 5 — Azure App Configuration

> This is how you update the active model name without redeploying code. It's your live config store.

1. **"+ Create a resource"** → search **"App Configuration"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Location**: `South Africa North`
   - **Resource name**: `agent-ochuko-appconfig`
   - **Pricing tier**: `Free` — up to 10MB of config, 1M requests/month
3. **Review + Create** → **Create**
**After creation — add keys**:
1. Go to resource → **"Configuration explorer"** → **"+ Create"** → **"Key-value"**
2. Add these keys one by one (with Label `production`):

**Model Deployments**

| Key | Value | Label | Notes |
|---|---|---|---|
| `THINK_MODEL_DEPLOYMENT` | `gpt-5.4` | `production` | THINK mode model |
| `SOLVE_MODEL_DEPLOYMENT` | `gpt-5.4-mini` | `production` | SOLVE mode model |
| `NANO_MODEL_DEPLOYMENT` | `gpt-5.4-nano` | `production` | DISCUSS/Nano interceptor model |
| `HUGGINGFACE_IMAGE_MODEL` | `black-forest-labs/FLUX.1-dev` | `production` | Hugging Face image model path |
| `SPEECH_VOICE_NAME` | `en-US-JennyNeural` | `production` | Azure Speech neural voice name |
| `COMPACTION_MODEL_DEPLOYMENT` | `o4-mini` | `production` | Compaction/summarizer model |

**Routing & Compaction**

| Key | Value | Label | Notes |
|---|---|---|---|
| `NANO_MAX_TURNS` | `3` | `production` | Turns before Nano hands off |
| `COMPACTION_THRESHOLD` | `50` | `production` | Message count to trigger GPT-4.0 Mini compaction |
| `REGISTRATION_LIMIT` | `100` | `production` | Max registered users limit |
| `MAINTENANCE_MODE` | `false` | `production` | Global maintenance toggle |
| `GLOBAL_DAILY_TOKEN_BUDGET` | `100000` | `production` | Max daily tokens across all users |

**System Prompts (Stored in App Config for live editing without redeploy)**

| Key | Value | Label | Notes |
|---|---|---|---|
| `THINK_PROMPT` | `[THINK Prompt Text]` | `production` | Deep analysis with reflection |
| `SOLVE_PROMPT` | `[SOLVE Prompt Text]` | `production` | Deterministic logic/maths |
| `DISCUSS_PROMPT` | `[DISCUSS Prompt Text]` | `production` | Warm, casual default chat |
| `NANO_PROMPT` | `[NANO Prompt Text]` | `production` | Concise 1-3 sentences interceptor |

**Collect credentials**:
```
AZURE_APP_CONFIG_CONNECTION_STRING=<your-app-config-connection-string>
```
> Get from: App Configuration → **"Access keys"** → copy "Read-only keys" → Connection string

---

## Service 6 — Azure Key Vault

> All your secrets live here. Your backend fetches them at startup. **Never put secrets in code.**

1. **"+ Create a resource"** → search **"Key Vault"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Key vault name**: `agent-ochuko-kv`
   - **Region**: `South Africa North`
   - **Pricing tier**: `Standard`
3. **Review + Create** → **Create**

**After creation — add all secrets**:
1. Go to resource → **"Secrets"** → **"+ Generate/Import"**
2. Add each secret individually:

```
Secret Name                           → Value
──────────────────────────────────────────────────────────────
AZURE-OPENAI-ENDPOINT                 → (from Step 1)
AZURE-OPENAI-API-KEY                  → (from Step 1)
AZURE-DOCUMENT-INTELLIGENCE-ENDPOINT → (from Service 1 above)
AZURE-DOCUMENT-INTELLIGENCE-KEY       → (from Service 1 above)
AZURE-VISION-ENDPOINT                 → (from Service 2 above)
AZURE-VISION-KEY                      → (from Service 2 above)
AZURE-SPEECH-KEY                      → (from Service 3 above)
AZURE-SPEECH-REGION                   → (from Service 3 above)
GROQ-API-KEY                          → (from groq.com dashboard)
HUGGINGFACE-API-KEYS                  → (comma-separated list of HF tokens)
AZURE-STORAGE-CONNECTION-STRING       → (from Service 4 above)
AZURE-QUEUE-NAME                      → agent-jobs
AZURE-APP-CONFIG-CONNECTION-STRING    → (from Service 5 above)
SUPABASE-URL                          → (from Step 3 guide)
SUPABASE-SERVICE-ROLE-KEY             → (from Step 3 guide)
SUPABASE-JWT-SECRET                   → (from Step 3 guide)
GOOGLE-OAUTH-CLIENT-ID                → (from Step 4 guide)
GOOGLE-OAUTH-CLIENT-SECRET            → (from Step 4 guide)
```

> [!CAUTION]
> Key Vault secret names use dashes (`-`), not underscores. Your FastAPI code will fetch these at startup and map them to environment variable names.

**Collect credentials** (for the backend to access Key Vault):
- You'll grant the Container App a **Managed Identity** so it can access Key Vault without storing any secret.
- This is covered in the Container App setup below.

---

## Service 7 — Azure Container Apps (for FastAPI Backend)

> This is where your Docker container runs.

1. **"+ Create a resource"** → search **"Container Apps"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Container app name**: `agent-ochuko-api`
   - **Region**: `South Africa North`
3. **Container Apps Environment**:
   - Create new → name: `agent-ochuko-env`
4. Under **"App settings"** → **Container**:
   - **Image source**: `Docker Hub` (for now — we'll update to Azure Container Registry later)
   - **Image and tag**: leave default for now
5. **Review + Create** → **Create**

**After creation — enable Managed Identity**:
1. Go to resource → **"Identity"** (in left menu)
2. Under **"System assigned"** tab → toggle to **"On"** → **Save**
3. Copy the **Object (principal) ID** shown — you'll need it for Key Vault access

Object (principal) ID=3d5c8611-af84-4ed4-a0bf-34d0e18d98ee

**Grant Key Vault access to Container App**:
1. Go back to your Key Vault (`agent-ochuko-kv`)
2. **"Access policies"** → **"+ Add Access Policy"**
3. **Secret permissions**: select `Get`, `List`
4. **Principal**: search for your Container App name → select it
5. **Add** → **Save**

---

## Service 8 — Azure Functions (for Background Jobs)

1. **"+ Create a resource"** → search **"Function App"** → **Create**
2. Fill in:
   - **Resource group**: `rg-ochuko`
   - **Function App name**: `agent-ochuko-functions`
   - **Publish**: `Code`
   - **Runtime stack**: `Python`
   - **Version**: `3.11`
   - **Region**: `South Africa North`
   - **OS**: `Linux`
   - **Plan type**: `Consumption (Serverless)` — pay per execution, very cheap
3. **Review + Create** → **Create**

**After creation**:
- Enable Managed Identity (same as above)
- Grant Key Vault access (same as above — repeat for Function App principal)

---

## ✅ Phase 0 Step 2 Complete When You Have:

- [ ] Document Intelligence resource created + credentials saved
- [ ] Computer Vision resource created + credentials saved
- [ ] Speech Services resource created (F0 free tier) + credentials saved
- [ ] Blob Storage created with `uploads`, `generated`, `exports` containers
- [ ] App Configuration created with all keys added (including THINK, SOLVE, NANO, HUGGINGFACE_IMAGE_MODEL, SPEECH_VOICE_NAME, and COMPACTION_MODEL_DEPLOYMENT)
- [ ] Key Vault created with ALL secrets added (including AZURE-SPEECH-KEY, AZURE-SPEECH-REGION, GROQ-API-KEY, and HUGGINGFACE-API-KEYS)
- [ ] Container Apps environment created with Managed Identity enabled
- [ ] Function App created with Managed Identity + Key Vault access
- [ ] All credentials stored in Key Vault (not on your computer!)

---

## Next Step

→ Proceed to `03_supabase_setup.md`
