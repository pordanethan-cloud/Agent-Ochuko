// src/components/Toast.tsx
/**
 * Lightweight success/error toast notification.
 * Auto-dismisses after 3 s.
 */
import { useEffect } from "react";
import { CheckCircle, XCircle } from "lucide-react";

interface ToastProps {
  message: string;
  type: "success" | "error";
  onDismiss: () => void;
}

export function Toast({ message, type, onDismiss }: ToastProps) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const isSuccess = type === "success";

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl border text-sm font-medium
        ${isSuccess
          ? "bg-green-900/80 border-green-700 text-green-200"
          : "bg-red-900/80 border-red-700 text-red-200"
        } backdrop-blur-sm animate-slide-up`}
    >
      {isSuccess
        ? <CheckCircle size={18} className="text-green-400 shrink-0" />
        : <XCircle     size={18} className="text-red-400 shrink-0" />
      }
      {message}
    </div>
  );
}
