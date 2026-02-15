'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { PaperAirplaneIcon, XMarkIcon, CpuChipIcon, FolderOpenIcon } from '@heroicons/react/24/outline';
import { useMentions, type MentionItem } from '../../hooks/useMentions';
import { useFileMentions } from '../../hooks/useFileMentions';
import { useWorkspaceShortcuts, type ShortcutSuggestion } from '../../hooks/useWorkspaceShortcuts';
import { MentionDropdown } from '../shared/MentionDropdown';
import { FileExplorerModal } from '../shared/FileExplorerModal';
import { WorkspaceShortcutDropdown } from '../Task/WorkspaceShortcutDropdown';
import { ShortcutResultsPanel } from '../Task/ShortcutResultsPanel';
import { getFileIcon, formatFileSize, formatRelativeTime, type DenFile, type FileReference } from '../../services/fileService';

interface ChatInputProps {
  onSubmit: (text: string, fileReferences?: FileReference[]) => Promise<void>;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSubmit,
  disabled = false,
  placeholder = 'Type a message...',
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isFileExplorerOpen, setIsFileExplorerOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // @ mentions (People + Agents)
  const {
    sections: mentionSections,
    flatItems: mentionFlatItems,
    isLoading: isMentionLoading,
    selectedIndex: mentionSelectedIndex,
    isOpen: isMentionOpen,
    selectedAgent,
    handleInputChange: handleMentionInputChange,
    handleKeyDown: handleMentionKeyDown,
    handleSelect: handleMentionSelect,
    handleClose: handleMentionClose,
    removeAgent,
  } = useMentions();

  // # file mentions
  const {
    suggestions: fileSuggestions,
    isLoading: isFileSearching,
    selectedIndex: fileSelectedIndex,
    isOpen: isFileDropdownOpen,
    fileReferences,
    handleInputChange: handleFileInputChange,
    handleKeyDown: handleFileKeyDown,
    handleSelect: handleFileSelect,
    handleClose: handleFileClose,
    addFileReferences,
    removeFileReference,
    removeAllFileReferences,
  } = useFileMentions();

  // / workspace shortcuts
  const {
    suggestions: shortcutSuggestions,
    isLoading: isShortcutLoading,
    selectedIndex: shortcutSelectedIndex,
    isDropdownOpen: isShortcutDropdownOpen,
    activeShortcut,
    results: shortcutResults,
    resultsError: shortcutError,
    hasMore: shortcutHasMore,
    isLoadingMore: shortcutIsLoadingMore,
    loadMore: shortcutLoadMore,
    handleInputChange: handleShortcutInputChange,
    handleKeyDown: handleShortcutKeyDown,
    handleSelect: handleShortcutSelect,
    handleClose: handleShortcutClose,
    executeCurrentShortcut,
    removeShortcut,
    clearResults: clearShortcutResults,
    refreshResults: refreshShortcutResults,
    isShortcutCommand,
  } = useWorkspaceShortcuts();

  const mentionDropdownRef = useRef<HTMLDivElement>(null);
  const fileDropdownRef = useRef<HTMLDivElement>(null);
  const shortcutDropdownRef = useRef<HTMLDivElement>(null);

  // Auto-focus textarea on mount and when re-enabled
  useEffect(() => {
    if (!disabled) {
      textareaRef.current?.focus();
    }
  }, [disabled]);

  const canSubmit = (text.trim().length > 0 || activeShortcut) && !isSubmitting && !disabled;

  const autoResize = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;

    let message = text.trim();

    // Check if this is a workspace shortcut command
    if (isShortcutCommand(message)) {
      await executeCurrentShortcut(message);
      return;
    }

    // Append any file references not already mentioned as #filename in the text
    for (const file of fileReferences) {
      if (!message.includes(`#${file.name}`)) {
        message += ` #${file.name}`;
      }
    }

    const refsToSend = fileReferences.length > 0 ? [...fileReferences] : undefined;
    setText('');
    removeAllFileReferences();
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }

    setIsSubmitting(true);
    try {
      await onSubmit(message.trim(), refsToSend);
    } finally {
      setIsSubmitting(false);
      textareaRef.current?.focus();
    }
  }, [canSubmit, onSubmit, text, fileReferences, isShortcutCommand, executeCurrentShortcut]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    const cursorPosition = e.target.selectionStart || 0;
    setText(newValue);
    autoResize();

    // Notify all hooks
    handleMentionInputChange(newValue, cursorPosition);
    handleFileInputChange(newValue, cursorPosition);
    handleShortcutInputChange(newValue, cursorPosition);
  };

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // Backspace to remove pills when input is empty
      if (e.key === 'Backspace' && !text) {
        if (activeShortcut) {
          e.preventDefault();
          removeShortcut();
          return;
        }
        if (selectedAgent) {
          e.preventDefault();
          removeAgent();
          return;
        }
      }

      // Priority 1: Shortcut dropdown
      if (isShortcutDropdownOpen) {
        const handled = handleShortcutKeyDown(e);
        if (handled && (e.key === 'Enter' || e.key === 'Tab') && shortcutSuggestions[shortcutSelectedIndex]) {
          const newText = handleShortcutSelect(shortcutSuggestions[shortcutSelectedIndex]);
          setText(newText);
          return;
        }
        if (handled) return;
      }

      // Priority 2: Mention dropdown
      if (isMentionOpen) {
        const handled = handleMentionKeyDown(e);
        if (handled && (e.key === 'Enter' || e.key === 'Tab') && mentionFlatItems[mentionSelectedIndex]) {
          const newText = handleMentionSelect(mentionFlatItems[mentionSelectedIndex]);
          setText(newText);
          return;
        }
        if (handled) return;
      }

      // Priority 3: File dropdown
      if (isFileDropdownOpen) {
        const handled = handleFileKeyDown(e);
        if (handled && (e.key === 'Enter' || e.key === 'Tab') && fileSuggestions[fileSelectedIndex]) {
          const newText = handleFileSelect(fileSuggestions[fileSelectedIndex]);
          setText(newText);
          return;
        }
        if (handled) return;
      }

      // Default Enter = submit
      const anyDropdownOpen = isMentionOpen || isFileDropdownOpen || isShortcutDropdownOpen;
      if (e.key === 'Enter' && !e.shiftKey && !anyDropdownOpen) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [
      text,
      activeShortcut,
      removeShortcut,
      selectedAgent,
      removeAgent,
      isShortcutDropdownOpen,
      handleShortcutKeyDown,
      shortcutSuggestions,
      shortcutSelectedIndex,
      handleShortcutSelect,
      isMentionOpen,
      handleMentionKeyDown,
      mentionFlatItems,
      mentionSelectedIndex,
      handleMentionSelect,
      isFileDropdownOpen,
      handleFileKeyDown,
      fileSuggestions,
      fileSelectedIndex,
      handleFileSelect,
      handleSubmit,
    ],
  );

  // Click handlers for dropdown items
  const handleMentionSelectClick = useCallback((item: MentionItem) => {
    const newText = handleMentionSelect(item);
    setText(newText);
    textareaRef.current?.focus();
  }, [handleMentionSelect]);

  const handleFileSelectClick = useCallback((file: DenFile) => {
    const newText = handleFileSelect(file);
    setText(newText);
    textareaRef.current?.focus();
  }, [handleFileSelect]);

  const handleShortcutSelectClick = useCallback((suggestion: ShortcutSuggestion) => {
    const newText = handleShortcutSelect(suggestion);
    setText(newText);
    textareaRef.current?.focus();
  }, [handleShortcutSelect]);

  return (
    <div>
      <div className="relative">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <div className="flex items-center gap-2 bg-[var(--muted)] border border-[var(--border)] rounded-lg px-3 py-2.5 focus-within:border-[var(--accent)] transition-colors">
              {/* Shortcut pill */}
              {activeShortcut && (
                <span className="inline-flex items-center gap-1.5 pl-2 pr-1 py-0.5 text-xs bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.5_0.2_180)] rounded border border-[oklch(0.65_0.25_180/0.3)] flex-shrink-0">
                  <span className="text-xs">
                    {activeShortcut.type === 'calendar' ? '📅' : activeShortcut.type === 'contacts' ? '👤' : '🤖'}
                  </span>
                  <span className="font-medium">{activeShortcut.label.replace('/', '')}</span>
                  <button
                    type="button"
                    onClick={removeShortcut}
                    className="p-0.5 rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                    aria-label={`Remove ${activeShortcut.label}`}
                  >
                    <XMarkIcon className="w-3 h-3" />
                  </button>
                </span>
              )}
              {/* Agent pill */}
              {selectedAgent && (
                <span className="inline-flex items-center gap-1.5 pl-2 pr-1 py-0.5 text-xs bg-[oklch(0.7_0.15_280/0.15)] text-[oklch(0.5_0.15_280)] rounded border border-[oklch(0.7_0.15_280/0.3)] flex-shrink-0">
                  <CpuChipIcon className="w-3 h-3" />
                  <span className="font-medium">{selectedAgent.name}</span>
                  <button
                    type="button"
                    onClick={removeAgent}
                    className="p-0.5 rounded hover:bg-[oklch(0.7_0.15_280/0.2)] transition-colors"
                    aria-label={`Remove agent ${selectedAgent.name}`}
                  >
                    <XMarkIcon className="w-3 h-3" />
                  </button>
                </span>
              )}
              <textarea
                ref={textareaRef}
                value={text}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                placeholder={activeShortcut ? `Search ${activeShortcut.type}...` : placeholder}
                disabled={isSubmitting || disabled}
                rows={1}
                enterKeyHint="send"
                className="flex-1 bg-transparent text-sm text-[var(--foreground)] placeholder-[var(--muted-foreground)] resize-none min-h-[24px] focus:outline-none disabled:opacity-50"
              />
            </div>

            {/* @ Mention Dropdown */}
            {isMentionOpen && (
              <div ref={mentionDropdownRef}>
                <MentionDropdown
                  sections={mentionSections}
                  selectedIndex={mentionSelectedIndex}
                  isLoading={isMentionLoading}
                  onSelect={handleMentionSelectClick}
                />
              </div>
            )}

            {/* # File Dropdown */}
            {isFileDropdownOpen && (
              <div
                ref={fileDropdownRef}
                className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden"
              >
                {isFileSearching ? (
                  <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
                    Searching files...
                  </div>
                ) : fileSuggestions.length > 0 ? (
                  <ul className="max-h-64 overflow-y-auto">
                    {fileSuggestions.map((file, index) => (
                      <li key={file.id}>
                        <button
                          type="button"
                          onClick={() => handleFileSelectClick(file)}
                          className={`
                            w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors
                            ${index === fileSelectedIndex
                              ? 'bg-[oklch(0.65_0.25_180/0.1)]'
                              : 'hover:bg-[var(--muted)]'
                            }
                          `}
                        >
                          <span className="text-lg flex-shrink-0">
                            {getFileIcon(file.content_type)}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-[var(--foreground)] truncate">
                              {file.name}
                            </div>
                            <div className="text-xs text-[var(--muted-foreground)]">
                              {formatFileSize(file.size_bytes)} · {formatRelativeTime(file.created_at)}
                            </div>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
                    No files found
                  </div>
                )}
                <div className="px-4 py-2 border-t border-[var(--border)] bg-[var(--muted)]">
                  <p className="text-xs text-[var(--muted-foreground)]">
                    <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">↑↓</kbd> navigate
                    {' · '}
                    <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">Enter</kbd> select
                    {' · '}
                    <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">Esc</kbd> close
                  </p>
                </div>
              </div>
            )}

            {/* / Shortcut Dropdown */}
            {isShortcutDropdownOpen && (
              <div ref={shortcutDropdownRef}>
                <WorkspaceShortcutDropdown
                  suggestions={shortcutSuggestions}
                  selectedIndex={shortcutSelectedIndex}
                  isLoading={isShortcutLoading}
                  onSelect={handleShortcutSelectClick}
                />
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setIsFileExplorerOpen(true)}
            className="flex-shrink-0 inline-flex items-center justify-center h-[42px] w-[42px] rounded-lg text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
            aria-label="Browse files"
            title="Browse files"
          >
            <FolderOpenIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={`
              flex-shrink-0 inline-flex items-center justify-center h-[42px] w-[42px] rounded-lg transition-colors
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
          </button>
        </div>
      </div>

      {/* File reference pills */}
      {fileReferences.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {fileReferences.map((file) => (
            <span
              key={file.id}
              className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 text-xs bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)] rounded border border-[oklch(0.65_0.25_180/0.2)]"
            >
              <span className="text-xs">{getFileIcon(file.content_type)}</span>
              <span className="font-medium">{file.name}</span>
              <button
                type="button"
                onClick={() => removeFileReference(file.name)}
                className="p-0.5 rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                aria-label={`Remove ${file.name}`}
              >
                <XMarkIcon className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Workspace Shortcut Results */}
      <ShortcutResultsPanel
        results={shortcutResults}
        error={shortcutError}
        isLoading={isShortcutLoading}
        onDismiss={clearShortcutResults}
        onDataChange={refreshShortcutResults}
        hasMore={shortcutHasMore}
        isLoadingMore={shortcutIsLoadingMore}
        onLoadMore={shortcutLoadMore}
      />

      {/* File Explorer Modal */}
      <FileExplorerModal
        isOpen={isFileExplorerOpen}
        onClose={() => setIsFileExplorerOpen(false)}
        onSelect={addFileReferences}
        selectedFileIds={new Set(fileReferences.map(f => f.id))}
      />
    </div>
  );
}
