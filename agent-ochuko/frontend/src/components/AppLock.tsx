import React, { useState, useEffect } from 'react'
import { Lock, X, Delete, ShieldCheck } from 'lucide-react'

interface AppLockProps {
  mode: 'unlock' | 'setup' | 'change' | 'disable'
  onSuccess: (newPin?: string) => void
  onClose?: () => void
}

export const AppLock: React.FC<AppLockProps> = ({ mode, onSuccess, onClose }) => {
  const [pin, setPin] = useState('')
  const [error, setError] = useState(false)
  const [step, setStep] = useState<'current' | 'new' | 'confirm'>('new')
  const [tempPin, setTempPin] = useState('')
  const [instruction, setInstruction] = useState('')

  useEffect(() => {
    if (mode === 'unlock') {
      setInstruction('Enter security PIN to unlock')
    } else if (mode === 'setup') {
      setStep('new')
      setInstruction('Create a new 4-digit security PIN')
    } else if (mode === 'change') {
      setStep('current')
      setInstruction('Enter current security PIN')
    } else if (mode === 'disable') {
      setStep('current')
      setInstruction('Enter current security PIN to disable')
    }
  }, [mode])

  const handleKeyPress = (num: string) => {
    if (pin.length >= 4) return
    const newPin = pin + num
    setPin(newPin)

    if (newPin.length === 4) {
      setTimeout(() => {
        handleSubmit(newPin)
      }, 150)
    }
  }

  const handleBackspace = () => {
    setPin(prev => prev.slice(0, -1))
  }

  const handleClear = () => {
    setPin('')
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key >= '0' && e.key <= '9') {
        handleKeyPress(e.key)
      } else if (e.key === 'Backspace') {
        handleBackspace()
      } else if (e.key === 'Escape' && onClose) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [pin, step, tempPin, mode])

  const handleSubmit = (enteredPin: string) => {
    const savedPin = localStorage.getItem('app_lock_pin') || ''

    if (mode === 'unlock') {
      if (enteredPin === savedPin) {
        onSuccess()
      } else {
        triggerError()
      }
    } else if (mode === 'setup') {
      if (step === 'new') {
        setTempPin(enteredPin)
        setPin('')
        setStep('confirm')
        setInstruction('Confirm your new security PIN')
      } else if (step === 'confirm') {
        if (enteredPin === tempPin) {
          localStorage.setItem('app_lock_pin', enteredPin)
          onSuccess(enteredPin)
        } else {
          triggerError()
          setPin('')
          setStep('new')
          setInstruction('PINs did not match. Enter new PIN again')
        }
      }
    } else if (mode === 'change') {
      if (step === 'current') {
        if (enteredPin === savedPin) {
          setPin('')
          setStep('new')
          setInstruction('Enter new 4-digit security PIN')
        } else {
          triggerError()
        }
      } else if (step === 'new') {
        setTempPin(enteredPin)
        setPin('')
        setStep('confirm')
        setInstruction('Confirm your new security PIN')
      } else if (step === 'confirm') {
        if (enteredPin === tempPin) {
          localStorage.setItem('app_lock_pin', enteredPin)
          onSuccess(enteredPin)
        } else {
          triggerError()
          setPin('')
          setStep('new')
          setInstruction('PINs did not match. Enter new PIN again')
        }
      }
    } else if (mode === 'disable') {
      if (enteredPin === savedPin) {
        localStorage.removeItem('app_lock_pin')
        onSuccess()
      } else {
        triggerError()
      }
    }
  }

  const triggerError = () => {
    setError(true)
    setPin('')
    if (navigator.vibrate) {
      navigator.vibrate(200)
    }
    setTimeout(() => setError(false), 500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-4">
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20%, 60% { transform: translateX(-6px); }
          40%, 80% { transform: translateX(6px); }
        }
        .shake-element {
          animation: shake 0.4s ease-in-out;
        }
      `}</style>

      <div className={`relative w-full max-w-sm rounded-3xl border border-[#1e2025] bg-[#0d0f11]/90 p-8 shadow-2xl backdrop-blur-xl transition duration-200 ${error ? 'shake-element border-red-500/30' : ''}`}>
        {onClose && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-1.5 rounded-full border border-[#1e2025] bg-[#161b22]/50 text-[#8e95a2] hover:text-brand-text hover:bg-white/5 transition"
            title="Cancel"
          >
            <X className="w-4 h-4" />
          </button>
        )}

        <div className="flex flex-col items-center text-center space-y-3 mb-8">
          <div className="w-12 h-12 rounded-2xl bg-[#c5a880]/10 border border-[#c5a880]/20 flex items-center justify-center">
            {mode === 'setup' || mode === 'change' ? (
              <ShieldCheck className="w-5 h-5 text-[#c5a880]" />
            ) : (
              <Lock className="w-5 h-5 text-[#c5a880]" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-brand-text">
              {mode === 'unlock' ? 'App Locked' :
               mode === 'setup' ? 'Set PIN Lock' :
               mode === 'change' ? 'Change PIN Lock' : 'Disable PIN Lock'}
            </h3>
            <p className="text-[12px] text-brand-muted/70 mt-1 h-5">{instruction}</p>
          </div>
        </div>

        <div className="flex justify-center gap-4 mb-8">
          {[0, 1, 2, 3].map(idx => (
            <div
              key={idx}
              className={`w-3.5 h-3.5 rounded-full border transition-all duration-150 ${
                idx < pin.length
                  ? 'bg-[#c5a880] border-[#c5a880] scale-110 shadow-lg shadow-[#c5a880]/20'
                  : 'bg-transparent border-[#1e2025]'
              }`}
            />
          ))}
        </div>

        <div className="grid grid-cols-3 gap-3 max-w-[280px] mx-auto">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(num => (
            <button
              key={num}
              onClick={() => handleKeyPress(num)}
              className="h-14 rounded-2xl border border-[#1e2025] bg-[#161b22]/30 hover:bg-[#161b22]/80 text-[18px] font-semibold text-brand-text active:scale-95 transition-all duration-100 flex items-center justify-center select-none"
            >
              {num}
            </button>
          ))}
          <button
            onClick={handleClear}
            className="h-14 rounded-2xl text-[11px] font-bold text-brand-muted/50 hover:text-brand-text hover:bg-white/5 active:scale-95 transition flex items-center justify-center uppercase tracking-widest select-none"
          >
            Clear
          </button>
          <button
            onClick={() => handleKeyPress('0')}
            className="h-14 rounded-2xl border border-[#1e2025] bg-[#161b22]/30 hover:bg-[#161b22]/80 text-[18px] font-semibold text-brand-text active:scale-95 transition-all duration-100 flex items-center justify-center select-none"
          >
            0
          </button>
          <button
            onClick={handleBackspace}
            className="h-14 rounded-2xl hover:bg-white/5 active:scale-95 transition text-[#8e95a2] hover:text-brand-text flex items-center justify-center select-none"
            title="Delete"
          >
            <Delete className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  )
}
