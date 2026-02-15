'use client';

import { useRef, useCallback } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { motion, AnimatePresence, type PanInfo } from 'framer-motion';
import { useIsMobile } from '../hooks/useMediaQuery';

interface MobileSheetProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  /** Title for screen readers */
  title?: string;
  /** Override the desktop max-width wrapper class (default: "max-w-md") */
  desktopMaxWidth?: string;
}

/**
 * MobileSheet — on mobile viewports renders as a bottom sheet with drag-to-dismiss.
 * On desktop viewports renders as a standard centered dialog.
 */
export function MobileSheet({ isOpen, onClose, children, title, desktopMaxWidth }: MobileSheetProps) {
  const isMobile = useIsMobile();
  const sheetRef = useRef<HTMLDivElement>(null);

  const handleDragEnd = useCallback(
    (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
      // Dismiss if dragged down past 100px or with high velocity
      if (info.offset.y > 100 || info.velocity.y > 500) {
        onClose();
      }
    },
    [onClose],
  );

  return (
    <Dialog.Root open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <AnimatePresence>
        {isOpen && (
          <Dialog.Portal forceMount>
            {/* Backdrop */}
            <Dialog.Overlay asChild>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
              />
            </Dialog.Overlay>

            {/* Content */}
            <Dialog.Content asChild>
              {isMobile ? (
                /* Bottom sheet on mobile */
                <motion.div
                  ref={sheetRef}
                  initial={{ y: '100%' }}
                  animate={{ y: 0 }}
                  exit={{ y: '100%' }}
                  transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                  drag="y"
                  dragConstraints={{ top: 0 }}
                  dragElastic={0.2}
                  onDragEnd={handleDragEnd}
                  className="fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] bg-[var(--card)] rounded-t-2xl shadow-xl border-t border-[var(--border)] flex flex-col overflow-hidden focus:outline-none pb-[env(safe-area-inset-bottom)]"
                >
                  {/* Drag handle */}
                  <div className="flex justify-center pt-3 pb-2 shrink-0 cursor-grab active:cursor-grabbing">
                    <div className="w-10 h-1 rounded-full bg-[var(--muted-foreground)]/30" />
                  </div>
                  {title && (
                    <Dialog.Title className="sr-only">{title}</Dialog.Title>
                  )}
                  <div className="flex-1 overflow-auto">
                    {children}
                  </div>
                </motion.div>
              ) : (
                /* Centered dialog on desktop */
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.15 }}
                  className="fixed inset-0 z-50 flex items-center justify-center focus:outline-none"
                >
                  {title && (
                    <Dialog.Title className="sr-only">{title}</Dialog.Title>
                  )}
                  <div className={`w-full ${desktopMaxWidth || 'max-w-md'} mx-4`}>
                    {children}
                  </div>
                </motion.div>
              )}
            </Dialog.Content>
          </Dialog.Portal>
        )}
      </AnimatePresence>
    </Dialog.Root>
  );
}
