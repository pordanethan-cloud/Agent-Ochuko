/**
 * useVoice.ts
 *
 * Self-contained voice dictation hook. Manages:
 *   - Microphone permission request
 *   - MediaRecorder (audio/webm with audio/mp4 fallback for Safari iOS)
 *   - Web Audio API AnalyserNode for real-time volume measurement (VAD waveform)
 *   - Voice Activity Detection: silence at < -50 dB for 1500 ms → chunk upload
 *   - Chunk upload to POST /v1/audio/transcriptions with retry-once on network error
 *   - Groq Whisper + Nano stitching is server-side — we just receive final text
 *   - Browser compatibility detection (hides mic button if MediaRecorder absent)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { supabase } from '../utils/supabaseClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// VAD parameters (from spec)
const SILENCE_THRESHOLD_DB = -50   // dB below which we consider silence
const SILENCE_DURATION_MS = 1500   // continuous silence before cutting a chunk
const ANALYSIS_INTERVAL_MS = 50    // how often we check volume (~20 fps)
const MAX_CHUNK_DURATION_MS = 28000 // never accumulate more than 28 s per chunk (Groq limit)

// Clamp RMS power to dB
function rmsToDb(rms: number): number {
  if (rms < 0.0001) return -100
  return 20 * Math.log10(rms)
}

// Read RMS from an AnalyserNode's time-domain data
function readRmsDb(analyser: AnalyserNode): number {
  const buf = new Uint8Array(analyser.fftSize)
  analyser.getByteTimeDomainData(buf)
  let sum = 0
  for (let i = 0; i < buf.length; i++) {
    const norm = (buf[i] - 128) / 128
    sum += norm * norm
  }
  return rmsToDb(Math.sqrt(sum / buf.length))
}

// Detect the best supported MIME type for the current browser
function detectMimeType(): string {
  if (typeof MediaRecorder === 'undefined') return 'audio/webm'
  if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) return 'audio/webm;codecs=opus'
  if (MediaRecorder.isTypeSupported('audio/webm')) return 'audio/webm'
  if (MediaRecorder.isTypeSupported('audio/mp4')) return 'audio/mp4'   // Safari iOS
  return ''
}

export type VoiceError =
  | 'browser_incompatible'
  | 'permission_denied'
  | 'transcription_failed'
  | null

export interface VoiceState {
  isRecording: boolean
  isTranscribing: boolean
  /** 0–1 normalised volume, updated ~20 fps. Drives the waveform overlay. */
  currentVolume: number
  /** Accumulated grammar-corrected transcript from all chunks so far */
  transcribedText: string
  error: VoiceError
  /** Feature detection result — if false, hide the mic button entirely */
  isSupported: boolean
  startRecording: () => Promise<void>
  stopRecording: () => void
  /** Reset transcript to '' (call when user manually edits the input bar) */
  clearTranscript: () => void
}

export function useVoice(onTextUpdate: (text: string) => void): VoiceState {
  // ── Feature detection (run once, stable) ─────────────────────────────────
  const isSupported =
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function'

  // ── State ─────────────────────────────────────────────────────────────────
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [currentVolume, setCurrentVolume] = useState(0)
  const [transcribedText, setTranscribedText] = useState('')
  const [error, setError] = useState<VoiceError>(null)

  // Internal refs — no re-render needed
  const streamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const silenceTimerRef = useRef<number | null>(null)
  const vadIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const chunkStartRef = useRef<number>(Date.now())
  const transcriptRef = useRef<string>('')          // mirrors transcribedText for stable closure
  const isRecordingActiveRef = useRef<boolean>(false)

  // ── Upload a chunk to the backend ─────────────────────────────────────────
  const uploadChunk = useCallback(async (blob: Blob): Promise<void> => {
    if (blob.size < 100) return  // ignore near-empty blobs

    const token = (await supabase.auth.getSession()).data.session?.access_token
    if (!token) return

    setIsTranscribing(true)

    const attemptUpload = async (): Promise<string> => {
      const form = new FormData()
      form.append('file', blob, blob.type.includes('mp4') ? 'chunk.mp4' : 'chunk.webm')
      form.append('existing_text', transcriptRef.current)

      const resp = await fetch(`${API_BASE}/v1/audio/transcriptions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      })

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      return data.text ?? ''
    }

    let newText = ''
    try {
      newText = await attemptUpload()
    } catch {
      // Retry once on network failure (spec requirement)
      try {
        newText = await attemptUpload()
      } catch {
        setError('transcription_failed')
        setIsTranscribing(false)
        // Non-fatal: keep recording, user sees a toast from the parent component
        return
      }
    } finally {
      setIsTranscribing(false)
    }

    if (newText) {
      transcriptRef.current = newText
      setTranscribedText(newText)
      onTextUpdate(newText)
    }
  }, [onTextUpdate])

  // ── Start a fresh MediaRecorder instance (ensures valid container headers) ──
  const startRecorderInstance = useCallback(() => {
    const stream = streamRef.current
    if (!stream) return

    const mimeType = detectMimeType()
    const recorderOptions = mimeType ? { mimeType } : {}
    const recorder = new MediaRecorder(stream, recorderOptions)
    recorderRef.current = recorder

    recorder.ondataavailable = (e: BlobEvent) => {
      if (e.data && e.data.size > 0) {
        const blob = new Blob([e.data], { type: mimeType || 'audio/webm' })
        uploadChunk(blob)
      }
    }

    recorder.onstop = () => {
      // Restart if we are still actively recording
      if (isRecordingActiveRef.current) {
        startRecorderInstance()
      }
    }

    recorder.onerror = () => {
      setError('transcription_failed')
    }

    chunkStartRef.current = Date.now()
    recorder.start()
  }, [uploadChunk])

  // ── Cut and upload the current accumulated audio segment ──────────────────
  const cutChunk = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state !== 'recording') return

    // Stopping the recorder flushes accumulated data and triggers restart in onstop
    recorder.stop()
  }, [])

  // ── VAD loop ──────────────────────────────────────────────────────────────
  const startVad = useCallback(() => {
    if (!analyserRef.current) return

    vadIntervalRef.current = setInterval(() => {
      if (!analyserRef.current) return

      const db = readRmsDb(analyserRef.current)
      // Normalise to 0–1 for the waveform (clamp between -80 and -10 dB)
      const vol = Math.max(0, Math.min(1, (db - (-80)) / (-10 - (-80))))
      setCurrentVolume(vol)

      const isSilent = db < SILENCE_THRESHOLD_DB

      if (isSilent) {
        if (silenceTimerRef.current === null) {
          // Start silence timer
          silenceTimerRef.current = window.setTimeout(() => {
            cutChunk()
            silenceTimerRef.current = null
          }, SILENCE_DURATION_MS)
        }
      } else {
        // Voice detected — cancel silence timer
        if (silenceTimerRef.current !== null) {
          clearTimeout(silenceTimerRef.current)
          silenceTimerRef.current = null
        }
      }

      // Also cut if chunk has been accumulating too long (safety valve)
      if (Date.now() - chunkStartRef.current > MAX_CHUNK_DURATION_MS) {
        cutChunk()
      }
    }, ANALYSIS_INTERVAL_MS)
  }, [cutChunk])

  const stopVad = useCallback(() => {
    if (vadIntervalRef.current) {
      clearInterval(vadIntervalRef.current)
      vadIntervalRef.current = null
    }
    if (silenceTimerRef.current !== null) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    setCurrentVolume(0)
  }, [])

  // ── Start recording ───────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    if (!isSupported) {
      setError('browser_incompatible')
      return
    }

    setError(null)
    setTranscribedText('')
    transcriptRef.current = ''
    isRecordingActiveRef.current = true

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    } catch {
      setError('permission_denied')
      isRecordingActiveRef.current = false
      return
    }

    streamRef.current = stream

    // Set up Web Audio for volume analysis
    const audioCtx = new AudioContext()
    audioCtxRef.current = audioCtx
    const source = audioCtx.createMediaStreamSource(stream)
    const analyser = audioCtx.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)
    analyserRef.current = analyser

    // Kick off first recorder instance
    startRecorderInstance()

    setIsRecording(true)
    startVad()
  }, [isSupported, startRecorderInstance, startVad])

  // ── Stop recording ────────────────────────────────────────────────────────
  const stopRecording = useCallback(() => {
    isRecordingActiveRef.current = false
    stopVad()

    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      try { recorder.stop() } catch { /* ignore */ }
    }
    recorderRef.current = null

    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null

    audioCtxRef.current?.close().catch(() => { /* ignore */ })
    audioCtxRef.current = null
    analyserRef.current = null

    setIsRecording(false)
  }, [stopVad])

  const clearTranscript = useCallback(() => {
    setTranscribedText('')
    transcriptRef.current = ''
  }, [])

  // ── Cleanup on unmount ────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      isRecordingActiveRef.current = false
      stopVad()
      streamRef.current?.getTracks().forEach(t => t.stop())
      audioCtxRef.current?.close().catch(() => { /* ignore */ })
    }
  }, [stopVad])

  return {
    isRecording,
    isTranscribing,
    currentVolume,
    transcribedText,
    error,
    isSupported,
    startRecording,
    stopRecording,
    clearTranscript,
  }
}
