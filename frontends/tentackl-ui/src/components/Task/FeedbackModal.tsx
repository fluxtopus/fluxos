'use client';

import { useState } from 'react';
import {
  XMarkIcon,
  FaceSmileIcon,
  FaceFrownIcon,
  ChatBubbleBottomCenterTextIcon,
} from '@heroicons/react/24/outline';
import { MobileSheet } from '../MobileSheet';

interface FeedbackModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (feedback: { rating: 'good' | 'bad'; comment?: string }) => void;
  isProcessing?: boolean;
}

/**
 * FeedbackModal - Collect outcome feedback after completion.
 * Quick, optional, not intrusive.
 */
export function FeedbackModal({
  isOpen,
  onClose,
  onSubmit,
  isProcessing = false,
}: FeedbackModalProps) {
  const [rating, setRating] = useState<'good' | 'bad' | null>(null);
  const [comment, setComment] = useState('');
  const [showComment, setShowComment] = useState(false);

  const handleSubmit = () => {
    if (rating) {
      onSubmit({ rating, comment: comment.trim() || undefined });
    }
  };

  const handleRating = (value: 'good' | 'bad') => {
    setRating(value);
    if (value === 'bad') {
      setShowComment(true);
    }
  };

  return (
    <MobileSheet isOpen={isOpen} onClose={onClose} title="How did it go?">
      <div className="bg-[var(--card)] rounded-2xl shadow-xl border border-[var(--border)] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <h2 className="text-lg font-semibold text-[var(--foreground)]">
            How did it go?
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-6">
          <p className="text-sm text-[var(--muted-foreground)] text-center mb-6">
            Your feedback helps me improve
          </p>

          {/* Rating buttons */}
          <div className="flex items-center justify-center gap-6 mb-6">
            <button
              onClick={() => handleRating('good')}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                rating === 'good'
                  ? 'border-[oklch(0.78_0.22_150)] bg-[oklch(0.7_0.2_150/0.1)]'
                  : 'border-[var(--border)] hover:border-[oklch(0.7_0.2_150/0.5)]'
              }`}
            >
              <FaceSmileIcon className={`w-10 h-10 ${
                rating === 'good' ? 'text-[oklch(0.78_0.22_150)]' : 'text-[var(--muted-foreground)]'
              }`} />
              <span className={`text-sm font-medium ${
                rating === 'good' ? 'text-[oklch(0.78_0.22_150)]' : 'text-[var(--muted-foreground)]'
              }`}>
                Good
              </span>
            </button>

            <button
              onClick={() => handleRating('bad')}
              className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all ${
                rating === 'bad'
                  ? 'border-[oklch(0.65_0.25_27)] bg-[oklch(0.65_0.25_27/0.1)]'
                  : 'border-[var(--border)] hover:border-[oklch(0.65_0.25_27/0.5)]'
              }`}
            >
              <FaceFrownIcon className={`w-10 h-10 ${
                rating === 'bad' ? 'text-[oklch(0.65_0.25_27)]' : 'text-[var(--muted-foreground)]'
              }`} />
              <span className={`text-sm font-medium ${
                rating === 'bad' ? 'text-[oklch(0.65_0.25_27)]' : 'text-[var(--muted-foreground)]'
              }`}>
                Not great
              </span>
            </button>
          </div>

          {/* Comment toggle and input */}
          {!showComment && rating === 'good' && (
            <button
              onClick={() => setShowComment(true)}
              className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] mx-auto"
            >
              <ChatBubbleBottomCenterTextIcon className="w-4 h-4" />
              Add a comment (optional)
            </button>
          )}

          {showComment && (
            <div className="mt-4">
              <label className="block text-sm font-medium text-[var(--foreground)] mb-2">
                {rating === 'bad' ? 'What could be better?' : 'Any comments?'}
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder={rating === 'bad' ? 'Tell me what went wrong...' : 'Optional feedback...'}
                rows={3}
                className="w-full px-3 py-2 text-sm bg-[var(--background)] border border-[var(--border)] rounded-lg focus:outline-none focus:border-[oklch(0.65_0.25_180/0.5)] text-[var(--foreground)] placeholder-[var(--muted-foreground)]"
              />
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-5 py-4 border-t border-[var(--border)] bg-[var(--muted)]/30 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            Skip
          </button>
          <button
            onClick={handleSubmit}
            disabled={!rating || isProcessing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
          >
            {isProcessing ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Sending...
              </>
            ) : (
              'Submit feedback'
            )}
          </button>
        </div>
      </div>
    </MobileSheet>
  );
}
