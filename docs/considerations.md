# Cross-Phase Considerations

> This file collects remaining unresolved architectural decisions, setup requirements, and configuration steps. Database migration tasks (C1, C4, C5) have been resolved, executed, and organized under the `scripts/` directory.

---

## C1 — Docker Hub Registry for Containers (Affects: Phase 7.3)

The CI/CD pipeline (`backend-deploy.yml`) is configured to push images to private Docker Hub repositories. The secrets `DOCKER_USERNAME` and `DOCKER_PASSWORD` must be configured in GitHub Secrets. No Azure Container Registry (ACR) setup is required.

---

## C2 — Model Expiry App Config Keys Not Defined (Affects: Phase 6.5)

The `model_expiry_monitor` cron reads these keys but they are not in the App Configuration setup in `02_azure_services_setup.md`. Add them manually after model deployments are created:

| Key | Value | Notes |
|---|---|---|
| `THINK_MODEL_EXPIRY_DATE` | `YYYY-MM-DD` | From Azure AI Foundry deployment details |
| `SOLVE_MODEL_EXPIRY_DATE` | `YYYY-MM-DD` | |
| `NANO_MODEL_EXPIRY_DATE` | `YYYY-MM-DD` | |
| `COMPACTION_MODEL_EXPIRY_DATE` | `YYYY-MM-DD` | |
| `THINK_FALLBACK_DEPLOYMENT` | e.g. `gpt-4o` | Deployment to auto-swap to on expiry |
| `SOLVE_FALLBACK_DEPLOYMENT` | e.g. `gpt-4o-mini` | |
| `NANO_FALLBACK_DEPLOYMENT` | e.g. `gpt-4o-mini` | |
| `COMPACTION_FALLBACK_DEPLOYMENT` | e.g. `gpt-4o-mini` | |

---

## C3 — Rate Limiting via Sticky Sessions (Affects: Phase 7.5)

Rate limiting is implemented using `slowapi` with in-memory storage (`memory://`). Consistency across multiple scaling Container App replicas is guaranteed by enabling **Session Affinity (sticky sessions)** on the Container App, ensuring a user's requests always route back to the same replica where their rate limits are tracked in-memory. Distributed caching like Redis is not required.

---

## C4 — Admin Dashboard Deployment and Chat Client Targets (Affects: Phase 5, Phase 7.3)

The static sites for both User Chat and the Admin Dashboard are deployed as Azure Storage Blob static website containers (`$web` on `agentochukostore` and `agentochukoadmin` storage accounts). SWA or Vercel are not used for hosting. Ensure CORS configuration targets:
* `https://agentochukostore.z1.web.core.windows.net`
* `https://agentochukoadmin.z1.web.core.windows.net`

---

## C5 — Synchronous Dictation Endpoint (`/v1/audio/transcriptions`) (Affects: Phase 9)

This endpoint is defined in `IMPLEMENTATION_PLAN.md` Section 7 but may not have been scaffolded in Phase 1 (Phase 1's task list does not explicitly mention it). Before Phase 9 voice work begins, verify the endpoint exists in `backend/app/api/v1/`. If not, implement:

```python
# backend/app/api/v1/audio.py
@router.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    existing_text: str = Form(default=""),
    user: UserContext = Depends(get_current_user)
) -> dict:
    """Synchronous dictation — Groq Whisper chunk + Nano stitching."""
    audio_bytes = await file.read()
    transcript = await groq_transcribe(audio_bytes)
    if existing_text:
        stitched = await nano_stitch(existing_text, transcript)
        return {"text": stitched}
    return {"text": transcript}
```

---

## C6 — TTS Browser Fallback (Affects: Phase 9)

The `02_azure_services_setup.md` document specifies a browser-native TTS fallback using `window.speechSynthesis` when Azure Speech is unavailable. This fallback must be implemented in the frontend. In `useJob.ts` or the TTS playback component:

```typescript
// If job fails with Azure Speech unavailable:
if (job.status === 'failed' && job.error?.includes('azure_speech')) {
  const utterance = new SpeechSynthesisUtterance(messageContent);
  window.speechSynthesis.speak(utterance);
}
```

---

## C7 — File Upload Path Clarification (Affects: Phase 2, Phase 7.5)

There are two distinct file upload paths to keep separate in the codebase:

| File Type | Upload Path |
|---|---|
| PDF, images (user uploads) | Frontend → Azure Blob via presigned URL (never through FastAPI) |
| Audio chunks (dictation) | Frontend → FastAPI → Groq API (FastAPI holds bytes in memory briefly) |

---

## C8 — Groq API Key Setup (Affects: Phase 4, Phase 9)

`GROQ-API-KEY` is required for voice operations. Setup steps:

1. Go to [https://console.groq.com](https://console.groq.com)
2. Create an API Key.
3. Save to Azure Key Vault as secret `GROQ-API-KEY`.

---

## C9 — Hugging Face API Keys Pool (Affects: Phase 4, Phase 7)

We use 5–6 Hugging Face API keys as a comma-separated string in Key Vault (`HUGGINGFACE-API-KEYS`). Each key must:

1. Be created at [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with **Read** scope.
2. Be associated with an account that has accepted the `FLUX.1-dev` model license at [https://huggingface.co/black-forest-labs/FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev) (otherwise, API returns `403 Forbidden`).

---

## Summary Table

| ID | Issue | Phases Affected | Severity |
|---|---|---|---|
| C1 | ACR not in Phase 0 setup | 7 | Medium |
| C2 | Model expiry App Config keys undefined | 6 | Medium |
| C3 | Rate limiting requires Azure Cache for Redis | 7 | Low (Cost Ignored) |
| C4 | Admin dashboard SWA vs Vercel mismatch | 5 | Low (clarity) |
| C5 | Dictation endpoint needs implementation | 9 | Medium |
| C6 | TTS browser fallback needs implementation | 9 | Low |
| C7 | File upload path clarification | 2, 7 | Low |
| C8 | Groq API key setup requirement | 4, 9 | Medium |
| C9 | Hugging Face license acceptance required | 4, 7 | Medium |
