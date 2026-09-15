import React from 'react'

interface ErrorBoundaryProps {
  children: React.ReactNode
  /** Optional custom fallback UI; defaults to a full-panel "something went wrong" screen. */
  fallback?: React.ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

/**
 * Catches render-time errors in its subtree and shows a recoverable fallback
 * instead of letting React 18 unmount the entire app (white screen).
 *
 * Without this, ANY render exception (bad file payload, undefined field, etc.)
 * blanks the whole UI. With it, only the affected region degrades.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep the stack in the console so production issues remain diagnosable.
    console.error('[ErrorBoundary] Caught render error:', error, '\nComponent stack:', info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback !== undefined) return this.props.fallback
      return (
        <div
          role="alert"
          style={{
            minHeight: '100dvh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            padding: 24,
            background: '#0d0f11',
            color: '#e2e5eb',
            fontFamily: 'system-ui, sans-serif',
            textAlign: 'center',
          }}
        >
          <h2 style={{ margin: 0, fontSize: 18 }}>Something went wrong</h2>
          <p style={{ margin: 0, fontSize: 14, opacity: 0.7, maxWidth: 420 }}>
            {this.state.error?.message || 'An unexpected error occurred while rendering the app.'}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '10px 20px',
              borderRadius: 10,
              border: '1px solid rgba(255,255,255,0.2)',
              background: 'rgba(255,255,255,0.1)',
              color: '#fff',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              minHeight: 44,
            }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
