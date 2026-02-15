'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { PaperAirplaneIcon, SparklesIcon, XMarkIcon, CpuChipIcon, FolderOpenIcon } from '@heroicons/react/24/outline';
import { useFileMentions } from '../../hooks/useFileMentions';
import { useMentions, type MentionItem } from '../../hooks/useMentions';
import { useWorkspaceShortcuts, type ShortcutSuggestion, type ActiveShortcut } from '../../hooks/useWorkspaceShortcuts';
import { getFileIcon, formatFileSize, formatRelativeTime, type DenFile, type FileReference } from '../../services/fileService';
import { MentionDropdown } from '../shared/MentionDropdown';
import { FileExplorerModal } from '../shared/FileExplorerModal';
import { WorkspaceShortcutDropdown } from './WorkspaceShortcutDropdown';
import { ShortcutResultsPanel } from './ShortcutResultsPanel';

interface NewTaskInputProps {
  onSubmit: (goal: string, fileReferences?: FileReference[], agentId?: string) => void;
  isLoading?: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  /** Hides example suggestions and keyboard hints (for embedded use). */
  compact?: boolean;
}

const exampleGoals = [
  "Summarize the top 10 HackerNews posts from today",
  "Find and organize all receipts from last month",
  "Create a weekly digest of my team's activity",
  "Research competitor pricing and summarize findings",
  "Generate social media posts for our product launch",
];

/**
 * NewTaskInput - The primary input for creating delegations.
 * Supports @ mentions (people/agents), # file references, and / workspace commands.
 */
export function NewTaskInput({
  onSubmit,
  isLoading = false,
  placeholder = "What would you like me to do?",
  autoFocus = false,
  compact = false,
}: NewTaskInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [showExamples, setShowExamples] = useState(true);
  const [isFileExplorerOpen, setIsFileExplorerOpen] = useState(false);
  // Use a ref for goal to avoid controlled input re-render issues
  const goalRef = useRef('');
  const [, forceUpdate] = useState(0); // Only for submit button enable/disable

  // File mentions hook
  const {
    suggestions: fileSuggestions,
    isLoading: isSearching,
    selectedIndex: fileSelectedIndex,
    isOpen: isFileDropdownOpen,
    fileReferences,
    handleInputChange: handleFileInputChange,
    handleKeyDown: handleFileKeyDown,
    handleSelect: handleFileSelect,
    handleClose: handleFileClose,
    removeFileReference,
    addFileReferences,
    extractFileReferences,
  } = useFileMentions();

  // @ mentions hook (People + Agents)
  const {
    sections: mentionSections,
    flatItems: mentionFlatItems,
    isLoading: isMentionLoading,
    selectedIndex: mentionSelectedIndex,
    isOpen: isMentionDropdownOpen,
    selectedAgent,
    handleInputChange: handleMentionInputChange,
    handleKeyDown: handleMentionKeyDown,
    handleSelect: handleMentionSelect,
    handleClose: handleMentionClose,
    removeAgent,
  } = useMentions();

  const mentionDropdownRef = useRef<HTMLDivElement>(null);

  // Workspace shortcuts hook
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

  const shortcutDropdownRef = useRef<HTMLDivElement>(null);

  // Focus textarea on mount when autoFocus is set
  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  // Auto-resize textarea
  const autoResize = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  // Close dropdowns on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        handleFileClose();
      }
      if (mentionDropdownRef.current && !mentionDropdownRef.current.contains(e.target as Node)) {
        handleMentionClose();
      }
      if (shortcutDropdownRef.current && !shortcutDropdownRef.current.contains(e.target as Node)) {
        handleShortcutClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [handleFileClose, handleMentionClose, handleShortcutClose]);

  // Handle text input change - uncontrolled to avoid React render loops
  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    const cursorPosition = e.target.selectionStart || 0;
    const hadValue = goalRef.current.length > 0;
    const hasValue = newValue.length > 0;
    goalRef.current = newValue;

    // Auto-resize
    autoResize();

    // Hide examples on first character
    if (!hadValue && hasValue) {
      setShowExamples(false);
    }

    // Update button state only when empty<->non-empty changes
    if (hadValue !== hasValue) {
      forceUpdate(n => n + 1);
    }

    // Handle # file mentions
    handleFileInputChange(newValue, cursorPosition);

    // Handle @ mentions (People + Agents)
    handleMentionInputChange(newValue, cursorPosition);

    // Handle / workspace shortcuts
    handleShortcutInputChange(newValue, cursorPosition);
  };

  // Handle form submission
  const handleSubmit = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    const goal = goalRef.current;
    if (goal.trim() && !isLoading) {
      // Check if this is a workspace shortcut command
      if (isShortcutCommand(goal.trim())) {
        // Execute the shortcut instead of submitting as a task
        await executeCurrentShortcut(goal.trim());
        return;
      }

      // Normal task submission
      const fileRefs = await extractFileReferences(goal);
      onSubmit(
        goal.trim(),
        fileRefs.length > 0 ? fileRefs : undefined,
        selectedAgent?.id,
      );
    }
  }, [isLoading, extractFileReferences, onSubmit, isShortcutCommand, executeCurrentShortcut, selectedAgent]);

  // Handle keyboard events
  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Handle backspace to remove agent/shortcut pill when input is empty
    if (e.key === 'Backspace' && !goalRef.current) {
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

    // First, check if shortcut dropdown is open and handle it
    if (isShortcutDropdownOpen) {
      const shortcutHandled = handleShortcutKeyDown(e);
      if (shortcutHandled && (e.key === 'Enter' || e.key === 'Tab') && shortcutSuggestions[shortcutSelectedIndex]) {
        const newText = handleShortcutSelect(shortcutSuggestions[shortcutSelectedIndex]);
        goalRef.current = newText;
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.value = newText;
          const newPosition = newText.length;
          textarea.setSelectionRange(newPosition, newPosition);
          textarea.focus();
          autoResize();
        }
        forceUpdate(n => n + 1);
        return;
      }
      if (shortcutHandled) return;
    }

    // Then, check if mention dropdown is open and handle it
    if (isMentionDropdownOpen) {
      const mentionHandled = handleMentionKeyDown(e);
      if (mentionHandled && (e.key === 'Enter' || e.key === 'Tab') && mentionFlatItems[mentionSelectedIndex]) {
        const newText = handleMentionSelect(mentionFlatItems[mentionSelectedIndex]);
        goalRef.current = newText;
        const textarea = textareaRef.current;
        if (textarea) {
          textarea.value = newText;
          const newPosition = newText.length;
          textarea.setSelectionRange(newPosition, newPosition);
          textarea.focus();
          autoResize();
        }
        forceUpdate(n => n + 1);
        return;
      }
      if (mentionHandled) return;
    }

    // Then, let file mention hook handle it
    const fileHandled = handleFileKeyDown(e);

    // If Enter/Tab was pressed and we have a file selection, do the selection
    if (fileHandled && (e.key === 'Enter' || e.key === 'Tab') && fileSuggestions[fileSelectedIndex]) {
      const newText = handleFileSelect(fileSuggestions[fileSelectedIndex]);
      goalRef.current = newText;
      // Update textarea value directly (uncontrolled)
      const textarea = textareaRef.current;
      if (textarea) {
        textarea.value = newText;
        const newPosition = newText.length;
        textarea.setSelectionRange(newPosition, newPosition);
        textarea.focus();
        autoResize();
      }
      forceUpdate(n => n + 1);
      return;
    }

    if (fileHandled) return;

    // Default Enter behavior (submit)
    const anyDropdownOpen = isFileDropdownOpen || isMentionDropdownOpen || isShortcutDropdownOpen;
    if (e.key === 'Enter' && !e.shiftKey && !anyDropdownOpen) {
      e.preventDefault();
      handleSubmit();
    }
  }, [
    handleFileKeyDown,
    handleMentionKeyDown,
    handleShortcutKeyDown,
    fileSuggestions,
    fileSelectedIndex,
    handleFileSelect,
    mentionFlatItems,
    mentionSelectedIndex,
    handleMentionSelect,
    shortcutSuggestions,
    shortcutSelectedIndex,
    handleShortcutSelect,
    isFileDropdownOpen,
    isMentionDropdownOpen,
    isShortcutDropdownOpen,
    handleSubmit,
    autoResize,
    activeShortcut,
    removeShortcut,
    selectedAgent,
    removeAgent,
  ]);

  // Handle file selection from dropdown click
  const handleFileSelectClick = useCallback((file: DenFile) => {
    const newText = handleFileSelect(file);
    goalRef.current = newText;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.value = newText;
      autoResize();
    }
    forceUpdate(n => n + 1);
    textarea?.focus();
  }, [handleFileSelect, autoResize]);

  // Handle mention selection from dropdown click
  const handleMentionSelectClick = useCallback((item: MentionItem) => {
    const newText = handleMentionSelect(item);
    goalRef.current = newText;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.value = newText;
      autoResize();
    }
    forceUpdate(n => n + 1);
    textarea?.focus();
  }, [handleMentionSelect, autoResize]);

  // Handle shortcut selection from dropdown click
  const handleShortcutSelectClick = useCallback((suggestion: ShortcutSuggestion) => {
    const newText = handleShortcutSelect(suggestion);
    goalRef.current = newText;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.value = newText;
      autoResize();
    }
    forceUpdate(n => n + 1);
    textarea?.focus();
  }, [handleShortcutSelect, autoResize]);

  // Handle example click
  const handleExampleClick = useCallback((example: string) => {
    goalRef.current = example;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.value = example;
      autoResize();
    }
    setShowExamples(false);
    forceUpdate(n => n + 1);
    textarea?.focus();
  }, [autoResize]);

  // Handle removing a file reference tag
  const handleRemoveFile = useCallback((filename: string) => {
    const newText = removeFileReference(filename);
    goalRef.current = newText;
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.value = newText;
      autoResize();
    }
    forceUpdate(n => n + 1);
    textarea?.focus();
  }, [removeFileReference, autoResize]);

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Main input */}
      <form onSubmit={handleSubmit} className="relative">
        <div className="relative rounded-2xl border-2 border-[var(--border)] bg-[var(--card)] focus-within:border-[oklch(0.65_0.25_180/0.5)] transition-colors shadow-sm">
          <div className="flex items-center gap-2 px-5 py-3">
            {/* Shortcut pill */}
            {activeShortcut && (
              <span className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 text-sm bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.5_0.2_180)] rounded-lg border border-[oklch(0.65_0.25_180/0.3)] flex-shrink-0">
                <span className="text-sm">
                  {activeShortcut.type === 'calendar' ? '📅' : activeShortcut.type === 'contacts' ? '👤' : '🤖'}
                </span>
                <span className="font-medium">{activeShortcut.label.replace('/', '')}</span>
                <button
                  type="button"
                  onClick={removeShortcut}
                  className="p-0.5 rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                  aria-label={`Remove ${activeShortcut.label}`}
                >
                  <XMarkIcon className="w-3.5 h-3.5" />
                </button>
              </span>
            )}
            {/* Agent pill */}
            {selectedAgent && (
              <span className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 text-sm bg-[oklch(0.7_0.15_280/0.15)] text-[oklch(0.5_0.15_280)] rounded-lg border border-[oklch(0.7_0.15_280/0.3)] flex-shrink-0">
                <CpuChipIcon className="w-3.5 h-3.5" />
                <span className="font-medium">{selectedAgent.name}</span>
                <button
                  type="button"
                  onClick={removeAgent}
                  className="p-0.5 rounded hover:bg-[oklch(0.7_0.15_280/0.2)] transition-colors"
                  aria-label={`Remove agent ${selectedAgent.name}`}
                >
                  <XMarkIcon className="w-3.5 h-3.5" />
                </button>
              </span>
            )}
            <textarea
              ref={textareaRef}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={activeShortcut ? `Search ${activeShortcut.type}...` : placeholder}
              disabled={isLoading}
              rows={1}
              enterKeyHint="send"
              className="flex-1 py-1 text-base bg-transparent resize-none focus:outline-none text-[var(--foreground)] placeholder-[var(--muted-foreground)] disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setIsFileExplorerOpen(true)}
              className="flex-shrink-0 p-2.5 rounded-xl text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] transition-colors"
              aria-label="Browse files"
              title="Browse files"
            >
              <FolderOpenIcon className="w-5 h-5" />
            </button>
            <button
              type="submit"
              disabled={(!goalRef.current.trim() && !activeShortcut) || isLoading}
              className={`
                flex-shrink-0 p-2.5 rounded-xl transition-all duration-200
                ${(goalRef.current.trim() || activeShortcut) && !isLoading
                  ? 'delegation-cta text-white'
                  : 'bg-[var(--muted)] text-[var(--muted-foreground)] cursor-not-allowed'
                }
              `}
            >
              {isLoading ? (
                <SparklesIcon className="w-5 h-5 animate-pulse" />
              ) : (
                <PaperAirplaneIcon className="w-5 h-5" />
              )}
            </button>
          </div>

          {/* # File Mention Dropdown */}
          {isFileDropdownOpen && (
            <div
              ref={dropdownRef}
              className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden"
            >
              {isSearching ? (
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

          {/* @ Mention Dropdown (People + Agents) */}
          {isMentionDropdownOpen && (
            <div ref={mentionDropdownRef}>
              <MentionDropdown
                sections={mentionSections}
                selectedIndex={mentionSelectedIndex}
                isLoading={isMentionLoading}
                onSelect={handleMentionSelectClick}
              />
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
      </form>

      {/* File Explorer Modal */}
      <FileExplorerModal
        isOpen={isFileExplorerOpen}
        onClose={() => setIsFileExplorerOpen(false)}
        onSelect={addFileReferences}
        selectedFileIds={new Set(fileReferences.map(f => f.id))}
      />

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

      {/* Selected file reference tags */}
      {fileReferences.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {fileReferences.map((file) => (
            <span
              key={file.id}
              className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 text-sm bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)] rounded-lg border border-[oklch(0.65_0.25_180/0.2)]"
            >
              <span className="text-sm">{getFileIcon(file.content_type)}</span>
              <span className="font-medium">{file.name}</span>
              <button
                type="button"
                onClick={() => handleRemoveFile(file.name)}
                className="p-0.5 rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                aria-label={`Remove ${file.name}`}
              >
                <XMarkIcon className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Example suggestions */}
      {!compact && showExamples && (
        <div className="mt-6">
          <p className="text-xs text-[var(--muted-foreground)] uppercase tracking-wide mb-3">
            Try something like...
          </p>
          <div className="flex flex-wrap gap-2">
            {exampleGoals.map((example, idx) => (
              <button
                key={idx}
                onClick={() => handleExampleClick(example)}
                className="px-3 py-1.5 text-sm text-[var(--foreground)] bg-[var(--muted)] hover:bg-[var(--border)] rounded-lg transition-colors text-left"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Keyboard hint */}
      {!compact && (
        <p className="mt-4 text-xs text-[var(--muted-foreground)] text-center">
          Press <kbd className="px-1.5 py-0.5 bg-[var(--muted)] rounded text-[10px] font-mono">Enter</kbd> to delegate
          {' · '}
          Type <kbd className="px-1.5 py-0.5 bg-[var(--muted)] rounded text-[10px] font-mono">@</kbd> to mention people or agents
          {' · '}
          Type <kbd className="px-1.5 py-0.5 bg-[var(--muted)] rounded text-[10px] font-mono">#</kbd> to reference files
          {' · '}
          Type <kbd className="px-1.5 py-0.5 bg-[var(--muted)] rounded text-[10px] font-mono">/</kbd> for workspace commands
        </p>
      )}
    </div>
  );
}
