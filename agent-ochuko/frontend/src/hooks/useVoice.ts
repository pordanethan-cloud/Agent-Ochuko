import { useState, useRef } from 'react';
import { supabase } from '../utils/supabaseClient';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface VoiceOptions {
  onTranscriptChange: (text: string) => void;
  silenceThresholdDb?: number; // e.g. -50 dB
  silenceDurationMs?: number;  // 1500ms default
  onError?: (msg: string) => void;
}

export const useVoice = ({
  onTranscriptChange,
  silenceThresholdDb = -50,
  silenceDurationMs = 1500,
  onError
}: VoiceOptions) => {
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [currentVolume, setCurrentVolume] = useState(0);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSilentRef = useRef(true);
  const fullTextRef = useRef('');

  // Starts recording audio and monitors voice activity
  const startListening = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Microphone access is not supported by your browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setIsListening(true);
      audioChunksRef.current = [];
      
      // Setup Web Audio API for Silence Detection (VAD)
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      source.connect(analyser);
      
      audioContextRef.current = audioCtx;
      analyserRef.current = analyser;

      // Detect supported mimeType
      let mimeType = 'audio/webm';
      if (typeof MediaRecorder !== 'undefined') {
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          if (MediaRecorder.isTypeSupported('audio/mp4')) {
            mimeType = 'audio/mp4';
          } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
            mimeType = 'audio/ogg';
          } else if (MediaRecorder.isTypeSupported('audio/wav')) {
            mimeType = 'audio/wav';
          } else {
            mimeType = ''; // Use browser default
          }
        }
      } else {
        throw new Error("MediaRecorder API is not supported in this browser.");
      }

      // Setup MediaRecorder
      const options = mimeType ? { mimeType } : undefined;
      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Upload the chunk if we have audio and are still in listening mode
        if (audioChunksRef.current.length > 0 && isListening) {
          const audioBlob = new Blob(audioChunksRef.current, { type: mimeType || 'audio/webm' });
          audioChunksRef.current = [];
          await uploadChunk(audioBlob);
        }

        // Restart recording for next chunk if listening is active
        if (isListening && mediaRecorderRef.current && mediaRecorderRef.current.state === 'inactive') {
          audioChunksRef.current = [];
          try {
            mediaRecorderRef.current.start(250);
          } catch (e) {
            console.warn("Failed to restart MediaRecorder:", e);
          }
        }
      };

      // Start recording
      mediaRecorder.start(250); // timeslice of 250ms chunks

      // Start volume/silence polling loop
      isSilentRef.current = true;
      monitorVolume(audioCtx, analyser);

    } catch (err: any) {
      console.error("Error accessing microphone:", err);
      if (onError) {
        onError(err.message || "Microphone access required for voice input");
      }
      stopListening();
    }
  };

  const stopListening = () => {
    setIsListening(false);
    setIsTranscribing(false);
    setCurrentVolume(0);
    
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch (e) {}
    }
    
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        audioContextRef.current.close();
      } catch (e) {}
    }

    // Stop all audio tracks from stream
    if (mediaRecorderRef.current && mediaRecorderRef.current.stream) {
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    }
  };

  const monitorVolume = (audioCtx: AudioContext, analyser: AnalyserNode) => {
    const checkVolume = () => {
      if (!isListening || audioCtx.state === 'closed') return;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(dataArray);

      // Calculate average amplitude
      const average = dataArray.reduce((sum, val) => sum + val, 0) / dataArray.length;
      // Map average (0-255) to dB scale
      const db = average > 0 ? 20 * Math.log10(average / 255) : -Infinity;
      setCurrentVolume(average);

      const isSilent = db < silenceThresholdDb;

      if (isSilent) {
        if (!isSilentRef.current) {
          isSilentRef.current = true;
          // Start silence duration timer
          silenceTimerRef.current = setTimeout(() => {
            // Trigger VAD cut — stop recorder, which fires onstop & uploads, then restart
            triggerChunkCut();
          }, silenceDurationMs);
        }
      } else {
        isSilentRef.current = false;
        if (silenceTimerRef.current) {
          clearTimeout(silenceTimerRef.current);
          silenceTimerRef.current = null;
        }
      }

      if (isListening) {
        requestAnimationFrame(checkVolume);
      }
    };

    requestAnimationFrame(checkVolume);
  };

  const triggerChunkCut = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      // Trigger stop, which will upload the current chunk and restart in onstop
      mediaRecorderRef.current.stop();
    }
  };

  const uploadChunk = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    const formData = new FormData();
    formData.append('file', audioBlob, 'chunk.webm');
    formData.append('existing_text', fullTextRef.current);
    
    try {
      const session = await supabase.auth.getSession();
      const token = session.data.session?.access_token;
      if (!token) throw new Error('Authentication session not found.');

      const response = await fetch(`${API_BASE}/v1/audio/transcriptions`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`
        },
        body: formData
      });
      
      if (!response.ok) {
        throw new Error('Transcription server error');
      }

      const data = await response.json();
      const newText = data.text || '';
      if (newText.trim()) {
        fullTextRef.current = newText;
        onTranscriptChange(newText);
      }
    } catch (err: any) {
      console.error("Transcription failed:", err);
      if (onError) {
        onError("Transcription failed — please try again");
      }
    } finally {
      setIsTranscribing(false);
    }
  };

  const clearTranscript = () => {
    fullTextRef.current = '';
    onTranscriptChange('');
  };

  const setTranscriptDirect = (text: string) => {
    fullTextRef.current = text;
    onTranscriptChange(text);
  };

  return {
    isListening,
    isTranscribing,
    currentVolume,
    startListening,
    stopListening,
    clearTranscript,
    setTranscriptDirect
  };
};
