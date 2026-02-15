'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { searchFiles, listRecentFiles, type DenFile, type FileReference, toFileReference } from '../services/fileService';

interface MentionState {
  isOpen: boolean;
  query: string;
  startIndex: number; // Where # starts in the text
}

interface UseFileMentionsOptions {
  debounceMs?: number;
}

interface UseFileMentionsReturn {
  // State
  suggestions: DenFile[];
  isLoading: boolean;
  selectedIndex: number;
  isOpen: boolean;

  // File references extracted from text
  fileReferences: FileReference[];

  // Handlers
  handleInputChange: (text: string, cursorPosition: number) => void;
  handleKeyDown: (e: React.KeyboardEvent) => boolean; // Returns true if event was handled
  handleSelect: (file: DenFile) => string; // Returns new text with file inserted
  handleClose: () => void;
  removeFileReference: (filename: string) => string; // Returns new text with #filename removed
  removeAllFileReferences: () => void; // Clear all file references (e.g. after submit)
  addFileReferences: (files: DenFile[]) => void; // Add files from file explorer modal
  // Utilities
  extractFileReferences: (text: string) => Promise<FileReference[]>;
}

/**
 * useFileMentions - Hook for # file mentions in text input
 *
 * Detects when user types #, shows file suggestions,
 * and handles selection/keyboard navigation.
 */
export function useFileMentions(options: UseFileMentionsOptions = {}): UseFileMentionsReturn {
  const { debounceMs = 300 } = options;

  // Mention state
  const [mentionState, setMentionState] = useState<MentionState>({
    isOpen: false,
    query: '',
    startIndex: -1,
  });

  // Suggestions
  const [suggestions, setSuggestions] = useState<DenFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Track file references (resolved from selections)
  const [fileReferences, setFileReferences] = useState<Map<string, FileReference>>(new Map());

  // Debounce timer
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Current text for reference
  const textRef = useRef<string>('');

  // Search for files
  const doSearch = useCallback(async (query: string) => {
    setIsLoading(true);
    try {
      const files = query.length > 0
        ? await searchFiles(query, 8)
        : await listRecentFiles(8);
      setSuggestions(files);
      setSelectedIndex(0);
    } catch (error) {
      console.error('File search failed:', error);
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Debounced search
  const searchDebounced = useCallback((query: string) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      doSearch(query);
    }, debounceMs);
  }, [doSearch, debounceMs]);

  // Handle input change - detect # mentions
  const handleInputChange = useCallback((text: string, cursorPosition: number) => {
    textRef.current = text;

    // Find if we're in a mention context (# before cursor)
    const textBeforeCursor = text.slice(0, cursorPosition);
    const lastHashIndex = textBeforeCursor.lastIndexOf('#');

    if (lastHashIndex === -1) {
      // No # found
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // Check if # is at start or after a space (not in middle of word)
    const charBeforeHash = lastHashIndex > 0 ? text[lastHashIndex - 1] : ' ';
    if (charBeforeHash !== ' ' && charBeforeHash !== '\n' && lastHashIndex !== 0) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // Check if there's a space after the query (mention completed)
    const textAfterHash = textBeforeCursor.slice(lastHashIndex + 1);
    if (textAfterHash.includes(' ')) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // We're in a mention context!
    const query = textAfterHash;
    setMentionState({
      isOpen: true,
      query,
      startIndex: lastHashIndex,
    });

    // Search for files
    searchDebounced(query);
  }, [searchDebounced]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent): boolean => {
    if (!mentionState.isOpen || suggestions.length === 0) {
      return false;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(i => Math.min(i + 1, suggestions.length - 1));
        return true;

      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(i => Math.max(i - 1, 0));
        return true;

      case 'Enter':
      case 'Tab':
        if (suggestions[selectedIndex]) {
          e.preventDefault();
          return true; // Signal that selection should happen
        }
        return false;

      case 'Escape':
        e.preventDefault();
        setMentionState({ isOpen: false, query: '', startIndex: -1 });
        return true;

      default:
        return false;
    }
  }, [mentionState.isOpen, suggestions, selectedIndex]);

  // Handle file selection
  const handleSelect = useCallback((file: DenFile): string => {
    const text = textRef.current;
    const { startIndex, query } = mentionState;

    // Replace #query with #filename
    const before = text.slice(0, startIndex);
    const after = text.slice(startIndex + 1 + query.length);
    const newText = `${before}#${file.name}${after}`;

    // Store the file reference
    setFileReferences(prev => {
      const next = new Map(prev);
      next.set(file.name, toFileReference(file));
      return next;
    });

    // Close the dropdown
    setMentionState({ isOpen: false, query: '', startIndex: -1 });

    return newText;
  }, [mentionState]);

  // Close dropdown
  const handleClose = useCallback(() => {
    setMentionState({ isOpen: false, query: '', startIndex: -1 });
  }, []);

  // Remove a file reference (and its @mention from text)
  const removeFileReference = useCallback((filename: string): string => {
    const text = textRef.current;

    // Remove from fileReferences map
    setFileReferences(prev => {
      const next = new Map(prev);
      next.delete(filename);
      return next;
    });

    // Remove #filename from text (with optional trailing space)
    const pattern = new RegExp(`#${filename.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s?`, 'g');
    return text.replace(pattern, '');
  }, []);

  // Clear all file references (e.g. after submit)
  const removeAllFileReferences = useCallback(() => {
    setFileReferences(new Map());
  }, []);

  // Add file references programmatically (from file explorer modal)
  const addFileReferences = useCallback((files: DenFile[]) => {
    setFileReferences(prev => {
      const next = new Map(prev);
      for (const file of files) {
        next.set(file.name, toFileReference(file));
      }
      return next;
    });
  }, []);

  // Extract file references from text + any added via modal
  const extractFileReferences = useCallback(async (text: string): Promise<FileReference[]> => {
    // Find all #mentions in text
    const mentionPattern = /#([^\s#]+)/g;
    const mentions: FileReference[] = [];
    const includedNames = new Set<string>();
    const unresolved: string[] = [];
    let match;

    while ((match = mentionPattern.exec(text)) !== null) {
      const filename = match[1];
      const ref = fileReferences.get(filename);
      if (ref) {
        mentions.push(ref);
        includedNames.add(filename);
      } else {
        unresolved.push(filename);
      }
    }

    // Resolve any #mentions not in the Map (typed manually, dropdown skipped)
    if (unresolved.length > 0) {
      await Promise.allSettled(
        unresolved.map(filename =>
          Promise.race([
            searchFiles(filename, 5),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error('timeout')), 3000)
            ),
          ]).then(results => {
            const exactMatch = results.find(f => f.name === filename);
            if (exactMatch) {
              mentions.push(toFileReference(exactMatch));
              includedNames.add(filename);
            }
          })
        )
      );
    }

    // Include files added via modal that don't have #mentions in text
    for (const [name, ref] of fileReferences) {
      if (!includedNames.has(name)) {
        mentions.push(ref);
      }
    }

    return mentions;
  }, [fileReferences]);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return {
    suggestions,
    isLoading,
    selectedIndex,
    isOpen: mentionState.isOpen,
    fileReferences: Array.from(fileReferences.values()),
    handleInputChange,
    handleKeyDown,
    handleSelect,
    handleClose,
    removeFileReference,
    removeAllFileReferences,
    addFileReferences,
    extractFileReferences,
  };
}
