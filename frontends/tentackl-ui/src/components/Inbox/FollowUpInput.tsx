'use client';

import { useState, useRef, useCallback } from 'react';
import { PaperAirplaneIcon } from '@heroicons/react/24/outline';

interface FollowUpInputProps {
  conversationId: string;
  onSubmit: (text: string) => Promise<void>;
  disabled?: boolean;
}

export function FollowUpInput({ conversationId, onSubmit, disabled = false }: FollowUpInputProps) {
  const [text, setText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSubmit = text.trim().length > 0 && !isSubmitting && !disabled;

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;

    setIsSubmitting(true);
    try {
      await onSubmit(text.trim());
      setText('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [canSubmit, onSubmit, text]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-resize
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div className="border-t border-[var(--border)] pt-4">
      <label className="block text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wider mb-2">
        Follow up:
      </label>

      <textarea
        ref={textareaRef}
        value={text}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder='e.g. "Email this digest to the team"'
        disabled={isSubmitting || disabled}
        rows={1}
        enterKeyHint="send"
        className="w-full bg-[var(--muted)] border border-[var(--border)] rounded-lg p-3 text-sm text-[var(--foreground)] placeholder-[var(--muted-foreground)] resize-none min-h-[48px] focus:outline-none focus:border-[var(--accent)] disabled:opacity-50 transition-colors"
      />

      <div className="flex justify-end mt-2">
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!canSubmit}
          className={`
            inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors
            ${canSubmit
              ? 'bg-[var(--accent)] text-[var(--accent-foreground)] hover:opacity-90'
              : 'bg-[var(--muted)] text-[var(--muted-foreground)] cursor-not-allowed'
            }
          `}
        >
          {isSubmitting ? (
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <PaperAirplaneIcon className="h-4 w-4" />
          )}
          Send
        </button>
      </div>
    </div>
  );
}
