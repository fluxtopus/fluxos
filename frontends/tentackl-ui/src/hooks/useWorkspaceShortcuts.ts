'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  parseShortcut,
  isShortcutStart,
  getShortcutSuggestions,
  executeShortcut,
  type ShortcutType,
  type ParsedShortcut,
} from '../services/workspaceService';
import type { StructuredDataContent } from '../types/structured-data';

export interface ShortcutSuggestion {
  type: ShortcutType;
  label: string;
  example: string;
  description: string;
}

export interface ActiveShortcut {
  type: ShortcutType;
  label: string;
}

interface ShortcutState {
  isOpen: boolean;
  query: string;
  startIndex: number;
}

interface UseWorkspaceShortcutsOptions {
  debounceMs?: number;
}

interface UseWorkspaceShortcutsReturn {
  // State
  suggestions: ShortcutSuggestion[];
  isLoading: boolean;
  selectedIndex: number;
  isDropdownOpen: boolean;
  activeShortcut: ActiveShortcut | null;

  // Results
  results: StructuredDataContent | null;
  resultsError: string | null;

  // Handlers
  handleInputChange: (text: string, cursorPosition: number) => void;
  handleKeyDown: (e: React.KeyboardEvent) => boolean; // Returns true if event was handled
  handleSelect: (suggestion: ShortcutSuggestion) => string; // Returns new text with shortcut inserted
  handleClose: () => void;
  executeCurrentShortcut: (query: string) => Promise<boolean>; // Returns true if executed
  removeShortcut: () => void; // Remove the active shortcut pill

  // Pagination
  hasMore: boolean;
  isLoadingMore: boolean;
  loadMore: () => Promise<void>;

  // Utilities
  clearResults: () => void;
  refreshResults: () => Promise<void>;
  isShortcutCommand: (text: string) => boolean;
}

/**
 * useWorkspaceShortcuts - Hook for / workspace slash commands in text input.
 *
 * Detects when user types /, shows command suggestions,
 * and handles execution of workspace queries.
 */
export function useWorkspaceShortcuts(
  options: UseWorkspaceShortcutsOptions = {}
): UseWorkspaceShortcutsReturn {
  const { debounceMs = 150 } = options;

  // Shortcut state
  const [shortcutState, setShortcutState] = useState<ShortcutState>({
    isOpen: false,
    query: '',
    startIndex: -1,
  });

  // Active shortcut pill
  const [activeShortcut, setActiveShortcut] = useState<ActiveShortcut | null>(null);

  // Suggestions
  const [suggestions, setSuggestions] = useState<ShortcutSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Results from executed shortcut
  const [results, setResults] = useState<StructuredDataContent | null>(null);
  const [resultsError, setResultsError] = useState<string | null>(null);

  // Pagination
  const PAGE_SIZE = 20;
  const [currentOffset, setCurrentOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Store last executed shortcut for refresh
  const lastShortcutRef = useRef<ParsedShortcut | null>(null);

  // Debounce timer
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Current text for reference
  const textRef = useRef<string>('');

  // Update suggestions based on query
  const updateSuggestions = useCallback((query: string) => {
    const newSuggestions = getShortcutSuggestions(query);
    setSuggestions(newSuggestions);
    setSelectedIndex(0);
  }, []);

  // Debounced suggestion update
  const updateSuggestionsDebounced = useCallback(
    (query: string) => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        updateSuggestions(query);
      }, debounceMs);
    },
    [updateSuggestions, debounceMs]
  );

  // Handle input change - detect / slash commands
  const handleInputChange = useCallback(
    (text: string, cursorPosition: number) => {
      textRef.current = text;

      // Clear results when typing
      if (results) {
        setResults(null);
        setResultsError(null);
      }

      // If we have an active shortcut pill, no need to detect / - just track query
      if (activeShortcut) {
        setShortcutState({ isOpen: false, query: '', startIndex: -1 });
        return;
      }

      // Check if text starts with / (slash command mode)
      const trimmedStart = text.trimStart();
      if (!trimmedStart.startsWith('/')) {
        setShortcutState({ isOpen: false, query: '', startIndex: -1 });
        return;
      }

      // Find the / position
      const slashIndex = text.indexOf('/');
      if (slashIndex === -1 || slashIndex > cursorPosition) {
        setShortcutState({ isOpen: false, query: '', startIndex: -1 });
        return;
      }

      // Get the query after /
      const textAfterSlash = text.slice(slashIndex);
      const spaceAfterCommand = textAfterSlash.indexOf(' ', 1);

      // If we haven't typed a space yet, show command suggestions
      // e.g., "/cal" -> show dropdown, "/calendar " -> close dropdown
      if (spaceAfterCommand === -1 || spaceAfterCommand > cursorPosition - slashIndex) {
        const query = textAfterSlash.slice(0, cursorPosition - slashIndex);
        setShortcutState({
          isOpen: true,
          query,
          startIndex: slashIndex,
        });
        updateSuggestionsDebounced(query);
      } else {
        // User has typed the full command with space - close dropdown
        setShortcutState({ isOpen: false, query: '', startIndex: -1 });
      }
    },
    [updateSuggestionsDebounced, results, activeShortcut]
  );

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent): boolean => {
      if (!shortcutState.isOpen || suggestions.length === 0) {
        return false;
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((i) => Math.min(i + 1, suggestions.length - 1));
          return true;

        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((i) => Math.max(i - 1, 0));
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
          setShortcutState({ isOpen: false, query: '', startIndex: -1 });
          return true;

        default:
          return false;
      }
    },
    [shortcutState.isOpen, suggestions, selectedIndex]
  );

  // Handle shortcut selection - sets active pill and clears input
  const handleSelect = useCallback(
    (suggestion: ShortcutSuggestion): string => {
      // Set the active shortcut pill
      setActiveShortcut({
        type: suggestion.type,
        label: suggestion.label,
      });

      // Close the dropdown
      setShortcutState({ isOpen: false, query: '', startIndex: -1 });

      // Return empty string - input is now just for the query
      return '';
    },
    []
  );

  // Close dropdown
  const handleClose = useCallback(() => {
    setShortcutState({ isOpen: false, query: '', startIndex: -1 });
  }, []);

  // Remove the active shortcut pill
  const removeShortcut = useCallback(() => {
    setActiveShortcut(null);
    setResults(null);
    setResultsError(null);
  }, []);

  // Execute the shortcut command
  // When there's an active pill, query is the raw query text (e.g., "warriors")
  // When there's no pill, query is the full text (e.g., "/calendar warriors")
  const executeCurrentShortcut = useCallback(async (query: string): Promise<boolean> => {
    let parsed: ParsedShortcut | null = null;

    if (activeShortcut) {
      // Build the full shortcut string from pill + query
      const fullCommand = query.trim()
        ? `${activeShortcut.label} ${query.trim()}`
        : activeShortcut.label;
      parsed = parseShortcut(fullCommand);
    } else {
      // Parse the full text directly
      parsed = parseShortcut(query);
    }

    if (!parsed) {
      return false;
    }

    // Store for refresh and pagination
    lastShortcutRef.current = parsed;

    // Reset pagination
    setCurrentOffset(0);
    setHasMore(false);
    setIsLoading(true);
    setResultsError(null);

    try {
      const response = await executeShortcut(parsed, PAGE_SIZE, 0);
      setResults(response);
      setHasMore(response.has_more === true);
      setCurrentOffset(PAGE_SIZE);
      return true;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to execute shortcut';
      setResultsError(message);
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [activeShortcut]);

  // Load more results (next page)
  const loadMore = useCallback(async () => {
    const lastShortcut = lastShortcutRef.current;
    if (!lastShortcut || !hasMore || isLoadingMore) return;

    setIsLoadingMore(true);

    try {
      const response = await executeShortcut(lastShortcut, PAGE_SIZE, currentOffset);

      // Append new data to existing results
      setResults((prev) => {
        if (!prev) return response;
        return {
          ...prev,
          data: [...(prev.data || []), ...(response.data || [])],
          total_count: (prev.total_count || 0) + (response.total_count || 0),
          has_more: response.has_more,
        };
      });

      setHasMore(response.has_more === true);
      setCurrentOffset((prev) => prev + PAGE_SIZE);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load more results';
      setResultsError(message);
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore, currentOffset]);

  // Refresh results by re-executing the last shortcut (resets to page 1)
  const refreshResults = useCallback(async () => {
    const lastShortcut = lastShortcutRef.current;
    if (!lastShortcut) return;

    setCurrentOffset(0);
    setHasMore(false);
    setIsLoading(true);
    setResultsError(null);

    try {
      const response = await executeShortcut(lastShortcut, PAGE_SIZE, 0);
      setResults(response);
      setHasMore(response.has_more === true);
      setCurrentOffset(PAGE_SIZE);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to refresh results';
      setResultsError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setResults(null);
    setResultsError(null);
  }, []);

  // Check if text is a shortcut command (or we have an active shortcut pill)
  const isShortcutCommand = useCallback((text: string): boolean => {
    // If we have an active shortcut pill, any input is a shortcut command
    if (activeShortcut) {
      return true;
    }
    return parseShortcut(text) !== null;
  }, [activeShortcut]);

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
    isDropdownOpen: shortcutState.isOpen,
    activeShortcut,
    results,
    resultsError,
    hasMore,
    isLoadingMore,
    loadMore,
    handleInputChange,
    handleKeyDown,
    handleSelect,
    handleClose,
    executeCurrentShortcut,
    removeShortcut,
    clearResults,
    refreshResults,
    isShortcutCommand,
  };
}
