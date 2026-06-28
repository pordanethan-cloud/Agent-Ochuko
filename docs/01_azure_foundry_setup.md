# Phase 0 — Step 1: Azure AI Foundry Setup

> **Goal**: Deploy your AI model on Azure AI Foundry and collect the endpoint + API key needed for the backend.
> **Time estimate**: 30–45 minutes
> **Where**: [https://ai.azure.com](https://ai.azure.com)

---

## Prerequisites

- Azure student subscription active
- Access to [portal.azure.com](https://portal.azure.com) — sign in with your Microsoft account
- Your subscription should show in the top right after login

---

## Step 1 — Open Azure AI Foundry

1. Go to [https://ai.azure.com](https://ai.azure.com)
2. Sign in with the same Microsoft account as your Azure subscription
3. You should land on the **Azure AI Foundry** home page

---

## Step 2 — Create a Hub (if you don't have one)

> A **Hub** is the top-level resource that holds your AI projects. If you already have one, skip to Step 3.

1. Click **"+ Create"** → **"Hub"**
2. Fill in:
   - **Subscription**: your student subscription
   - **Resource group**: create new → name it `rg-ochuko`
   - **Hub name**: `agent-ochuko-hub`
   - **Region**: `South Africa North`
   - **Azure AI Services**: Create new → name it `agent-ochuko-ai-services`
3. Click **Review + Create** → **Create**
4. Wait for deployment (2–5 minutes)

> [!NOTE]
> South Africa North has limited model availability. If a model is not available there, you may need to use **Sweden Central** or **East US** as a secondary region. Check model availability at: https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models

---

## Step 3 — Create a Project

1. Inside your hub, click **"+ New Project"**
2. Fill in:
   - **Project name**: `agent-ochuko-app`
3. Click **Create**

---

## Step 4 — Deploy the Required Models

To power the 4-mode architecture (THINK, SOLVE, DISCUSS, Nano interceptor, and Compaction), you need to deploy **5 separate models** in your project's model catalog.

For each model below, search for it in the **"Model catalog"** (left sidebar), click **"Deploy"** → **"Deploy to Azure OpenAI"**, and fill in the details:

1. **THINK Mode Model**
   - **Model**: `gpt-5.4` (or latest reasoning/flagship model)
   - **Deployment name**: `gpt-5.4`
   - **Deployment type**: `Standard`
   - **TPM limit**: E.g., `10K` (keeps budget in check)

2. **SOLVE Mode Model**
   - **Model**: `gpt-5.4-mini` (or latest mini flagship)
   - **Deployment name**: `gpt-5.4-mini`
   - **Deployment type**: `Standard`
   - **TPM limit**: E.g., `20K`

3. **DISCUSS & Nano Interceptor Model**
   - **Model**: `gpt-5.4-nano` (or most cost-efficient light model)
   - **Deployment name**: `gpt-5.4-nano`
   - **Deployment type**: `Standard`
   - **TPM limit**: E.g., `30K`

4. **TTS (Text-to-Speech) Model**
   - **Model**: `tts-1` (Azure OpenAI Neural Text-to-Speech)
   - **Deployment name**: `tts-1-ochuko`
   - **Deployment type**: `Standard`

5. **Compaction/Summarizer Model**
   - **Model**: `o4-mini` (GPT-o4-mini)
   - **Deployment name**: `o4-mini`
   - **Deployment type**: `Standard`
   - **TPM limit**: E.g., `10K` (keeps costs extremely low for background jobs)

> [!IMPORTANT]
> Name these deployments exactly as shown above. These deployment names are referenced directly in your Azure App Configuration and code.

---

## Step 5 — Collect Your Credentials

Go to your project → **"Settings"** or click on any deployment → **"Endpoint"**

Write down these values (you'll need them for Azure Key Vault and your `.env` file):

```
AZURE_OPENAI_ENDPOINT=https://<your-hub>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your api key here>
AZURE_OPENAI_API_VERSION=2025-03-01-preview
THINK_MODEL_DEPLOYMENT=gpt-5.4
SOLVE_MODEL_DEPLOYMENT=gpt-5.4-mini
NANO_MODEL_DEPLOYMENT=gpt-5.4-nano
SPEECH_TTS_DEPLOYMENT=tts-1-ochuko
COMPACTION_MODEL_DEPLOYMENT=o4-mini
```

> [!CAUTION]
> **NEVER** put these keys directly in code or push them to GitHub. They go into Azure Key Vault (Step 3 guide).

---

## Step 6 — Test Your Deployments (Optional but Recommended)

1. In Foundry, open any deployment
2. Click **"Open in playground"**
3. Type a test message and verify you get a response
4. Check the **"Response"** tab to see the Responses API format

---

## Step 7 — Check Your Quota

1. Go to your Azure portal: [portal.azure.com](https://portal.azure.com)
2. Search for **"Azure OpenAI"** in the top search bar
3. Click on your Azure OpenAI resource (the one Foundry created)
4. Go to **"Quotas"** in the left menu
5. Note your TPM (tokens per minute) limit for each model

> [!WARNING]
> Student subscriptions have strict quota limits. If you hit them, users will get errors. The per-user token budget system in Agent Ochuko is designed to prevent this.

---

## ✅ Phase 0 Step 1 Complete When You Have:

- [ ] Hub created in `South Africa North`
- [ ] Project `agent-ochuko-app` created
- [ ] All 5 required models deployed (`gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `tts-1-ochuko`, `o4-mini`)
- [ ] Endpoint URL copied
- [ ] API Key copied
- [ ] Deployment names written down

---

## Next Step

→ Proceed to `02_azure_services_setup.md`
