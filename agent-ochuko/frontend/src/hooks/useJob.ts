/**
 * useJob.ts
 *
 * Generic async job polling hook. Polls GET /v1/agents/job/{job_id} every 2 s
 * until the job reaches a terminal state ('done' or 'failed'), times out after
 * 30 polls (~60 s), or the component unmounts (safe cleanup — no memory leaks).
 *
 * Used by the TTS playback path and any future async agents that return 202.
 */

import { useEffect, useRef, useState } from 'react'
import { supabase } from '../utils/supabaseClient'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Terminal states — polling stops when we reach one of these
const TERMINAL_STATES = new Set(['done', 'failed'])

export type JobStatus = 'pending' | 'processing' | 'done' | 'failed' | null

export interface JobState {
  status: JobStatus
  resultBlobUrl: string | null
  errorMessage: string | null
}

/**
 * Polls the job status endpoint every 2 s while *jobId* is non-null.
 *
 * @param jobId  The job UUID to poll, or null to idle
 *
 * Resets automatically when jobId changes (e.g. user clicks Listen on a
 * different message while the previous TTS is still pending).
 */
export function useJob(jobId: string | null): JobState {
  const [state, setState] = useState<JobState>({
    status: null,
    resultBlobUrl: null,
    errorMessage: null,
  })

  // Stable ref so the interval callback always reads the latest jobId
  const jobIdRef = useRef<string | null>(jobId)
  const pollCountRef = useRef<number>(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset state whenever jobId changes
  useEffect(() => {
    jobIdRef.current = jobId
    pollCountRef.current = 0

    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    if (!jobId) {
      setState({ status: null, resultBlobUrl: null, errorMessage: null })
      return
    }

    // Immediately mark as pending before first poll
    setState({ status: 'pending', resultBlobUrl: null, errorMessage: null })

    const poll = async () => {
      const currentJobId = jobIdRef.current
      if (!currentJobId) return

      // Timeout guard: 30 polls × 2 s = 60 s max wait
      pollCountRef.current += 1
      if (pollCountRef.current > 30) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
        setState({
          status: 'failed',
          resultBlobUrl: null,
          errorMessage: 'Request timed out. The audio may still be generating — please try again.',
        })
        return
      }

      try {
        const session = await supabase.auth.getSession()
        const token = session.data.session?.access_token
        if (!token) return

        const response = await fetch(`${API_BASE}/v1/agents/job/${currentJobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        })

        if (!response.ok) {
          // Non-fatal on transient errors — keep polling
          if (response.status >= 500) return
          // 404 or auth errors are terminal
          throw new Error(`Job lookup failed: ${response.status}`)
        }

        const data = await response.json()
        const { status, result_blob_url, error_message } = data

        if (TERMINAL_STATES.has(status)) {
          // Stop polling on terminal state
          if (intervalRef.current) {
            clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          setState({
            status: status as JobStatus,
            resultBlobUrl: result_blob_url ?? null,
            errorMessage: error_message ?? null,
          })
        } else {
          // Still pending or processing — update status label but keep polling
          setState(prev => ({
            ...prev,
            status: status as JobStatus,
          }))
        }
      } catch (err) {
        // Transient network error — keep polling, don't abort
        console.warn('[useJob] Poll error (will retry):', err)
      }
    }

    // Kick off immediately, then repeat every 2 s
    poll()
    intervalRef.current = setInterval(poll, 2000)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [jobId])

  return state
}
