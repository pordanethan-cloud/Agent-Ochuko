# Phase 9 — Voice UI Polish

> **Duration**: 2–3 days
> **Depends on**: Phase 4 (speech workers: `speech_stt_worker`, `speech_tts_worker` deployed), Phase 2 (InputBar component exists), Phase 8 (mode toggle in UI)

---

## 9.1 — Dictation Input (Day 1)

- [ ] Integrate `useVoice.ts` hook (fully specified in implementation plan Section 9) into `InputBar.tsx`
- [ ] Add microphone button in the input bar — toggles recording on/off
- [ ] Visual state when recording:
  - Input bar text blurs slightly (connotes voice mode, not typing)
  - Subtle pulsating waveform overlay driven by `currentVolume` from the hook's Web Audio API analyser
  - Small "listening..." label below or beside the input bar
- [ ] **VAD (Voice Activity Detection)** via Web Audio API:
  - Silence threshold: `-50 dB`
  - Silence duration: `1500ms` → triggers chunk cut
  - Chunk uploaded to `POST /v1/audio/transcriptions` (synchronous, Groq Whisper Large v3 Turbo)
  - Backend receives chunk + `existing_text` → stitches using Nano model (GPT-5.4 Nano) for grammar/capitalization correction → returns unified text
  - Result replaces input bar text incrementally
- [ ] Stop button: finalizes recording, uploads last chunk, text appears in input bar ready to send
- [ ] User can edit the transcribed text before sending — voice input is always editable

---

## 9.2 — TTS Playback (Day 1–2)

- [ ] Add a play button to every assistant message bubble
- [ ] Click → `POST /v1/agents/speech/tts` with `{text: message.content, voice: "en-ZA-LeahNeural"}`
- [ ] Returns `202 Accepted` → subscribe via `useJob.ts` → when `status = 'done'`, `result_blob_url` points to the generated audio blob in Azure Blob Storage
- [ ] Stream audio from blob URL using `<audio>` element — auto-play when ready
- [ ] Show small audio waveform / progress bar while playing
- [ ] Stop button to cancel playback mid-audio
- [ ] TTS voice name (`en-ZA-LeahNeural`) is configurable via Azure App Configuration key `SPEECH_VOICE_NAME` — already set in Phase 0

---

## 9.3 — Edge Cases & Permissions (Day 2)

- [ ] **Microphone permission denied**: show toast "Microphone access required for voice input" — do not crash
- [ ] **Browser incompatibility** (no MediaRecorder API): hide voice button entirely via feature detection
- [ ] **Network drop during chunk upload**: retry once, then show error toast "Transcription failed — please try again", continue recording
- [ ] **Mobile compatibility**:
  - Chrome Android: `audio/webm` works — default
  - Safari iOS: `MediaRecorder` may only support `audio/mp4` — detect and set `mimeType: 'audio/mp4'` as fallback
  - Test on both before marking phase complete

---

## Milestone

Full voice loop working. User speaks → text appears incrementally in input bar, grammar-corrected → user sends → assistant responds → user clicks play → hears the response in a South African English neural voice. Claude-style dictation experience.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional context.

### STT Is Dual-Mode: Synchronous Dictation vs Async Queue

The implementation plan defines two distinct STT paths:
- **`POST /v1/audio/transcriptions`** (Section 7): **synchronous** — for real-time dictation chunks. Uses Groq Whisper directly in FastAPI, returns text immediately.
- **`POST /v1/agents/speech/stt`** (Section 7): **async queue** — for heavy file transcription. Creates a job, returns `202`, uses `speech_stt_worker` Azure Function.

Phase 9.1 (dictation input) uses the **synchronous** endpoint only. The async queue path (`speech_stt_worker`) was deployed in Phase 4 and is used when a user uploads a full audio file for transcription, not for dictation. Keep these paths separate — do not route dictation chunks through the queue.

### TTS Fallback to Browser `window.speechSynthesis`

The `02_azure_services_setup.md` document specifies a browser-native TTS fallback: if Azure Speech is offline or the user exhausts the 500,000 free characters/month, the frontend falls back to `window.speechSynthesis`. Implement this fallback in the TTS playback path:
1. Call `POST /v1/agents/speech/tts` as normal
2. If job returns `status = 'failed'` with error indicating Azure Speech is unavailable → fall back to `window.speechSynthesis.speak(new SpeechSynthesisUtterance(message.content))`

### Voice in Phase 4 vs Phase 9

Phase 4 includes the task: "Voice UI: record button → blob → enqueue STT job → transcript into input bar". Phase 9 re-implements this with proper VAD, chunking, and stitching via the synchronous dictation endpoint. Phase 4's task was a basic placeholder; Phase 9 is the polished production version. If Phase 4 built the async-queue version, replace it with the synchronous VAD flow described in 9.1.

### `POST /v1/audio/transcriptions` Endpoint Not in `07_api_contract.md`

The synchronous dictation endpoint is defined in the implementation plan (Section 7) but may not have been scaffolded in Phase 1. Confirm it exists in `backend/app/api/v1/` — if not, add it before Phase 9 work begins. It is a multipart form endpoint:
```python
@router.post("/v1/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    existing_text: str = Form(default="")
) -> dict:
    # Call Groq Whisper, stitch with existing_text via Nano model
    ...
```
