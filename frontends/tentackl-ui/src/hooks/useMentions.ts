'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { getContacts, getContactsByName } from '../services/workspaceService';
import { listAgents } from '../services/agentApi';
import type { Contact } from '../types/structured-data';
import type { AgentSpec } from '../types/agent';

// ============================================
// Types
// ============================================

export type MentionItemType = 'contact' | 'agent';

export interface MentionItem {
  id: string;
  name: string;
  type: MentionItemType;
  description?: string;
  contact?: Contact;
  agent?: AgentSpec;
}

export interface MentionSection {
  title: string;
  items: MentionItem[];
}

interface MentionState {
  isOpen: boolean;
  query: string;
  startIndex: number;
}

interface UseMentionsReturn {
  // State
  sections: MentionSection[];
  flatItems: MentionItem[];
  isLoading: boolean;
  selectedIndex: number;
  isOpen: boolean;

  // Selected agent (pill — only one at a time)
  selectedAgent: AgentSpec | null;

  // Handlers
  handleInputChange: (text: string, cursorPosition: number) => void;
  handleKeyDown: (e: React.KeyboardEvent) => boolean;
  handleSelect: (item: MentionItem) => string;
  handleClose: () => void;
  removeAgent: () => void;
}

/**
 * useMentions - Hook for @ mentions in text input.
 *
 * Detects when user types @, shows a combined dropdown with
 * two sections: "People" (contacts) and "Agents".
 * Only one agent can be selected at a time (rendered as a pill).
 * Multiple contacts can be mentioned inline.
 */
export function useMentions(): UseMentionsReturn {
  // Mention state
  const [mentionState, setMentionState] = useState<MentionState>({
    isOpen: false,
    query: '',
    startIndex: -1,
  });

  // Suggestions
  const [sections, setSections] = useState<MentionSection[]>([]);
  const [flatItems, setFlatItems] = useState<MentionItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Selected agent (only one at a time)
  const [selectedAgent, setSelectedAgent] = useState<AgentSpec | null>(null);

  // Debounce timer
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Current text for reference
  const textRef = useRef<string>('');

  // Search for contacts and agents in parallel
  const doSearch = useCallback(async (query: string) => {
    setIsLoading(true);
    try {
      const [contactsResult, agentsResult] = await Promise.allSettled([
        query.length > 0
          ? getContactsByName(query)
          : getContacts(10),
        listAgents(undefined, undefined, true, true),
      ]);

      const contactItems: MentionItem[] = [];
      const agentItems: MentionItem[] = [];

      // Process contacts
      if (contactsResult.status === 'fulfilled' && contactsResult.value.data) {
        const contacts = contactsResult.value.data as Contact[];
        for (const contact of contacts.slice(0, 5)) {
          contactItems.push({
            id: contact.id || contact.name,
            name: contact.name,
            type: 'contact',
            description: contact.company || contact.email,
            contact,
          });
        }
      }

      // Process agents
      if (agentsResult.status === 'fulfilled') {
        const agents = agentsResult.value.agents;
        const filtered = query.length > 0
          ? agents.filter((a) =>
              a.name.toLowerCase().includes(query.toLowerCase()) ||
              a.description?.toLowerCase().includes(query.toLowerCase())
            )
          : agents;
        for (const agent of filtered.slice(0, 5)) {
          agentItems.push({
            id: agent.id,
            name: agent.name,
            type: 'agent',
            description: agent.description,
            agent,
          });
        }
      }

      const newSections: MentionSection[] = [];
      if (contactItems.length > 0) {
        newSections.push({ title: 'People', items: contactItems });
      }
      if (agentItems.length > 0) {
        newSections.push({ title: 'Agents', items: agentItems });
      }

      const flat = newSections.flatMap((s) => s.items);
      setSections(newSections);
      setFlatItems(flat);
      setSelectedIndex(0);
    } catch (error) {
      console.error('Mention search failed:', error);
      setSections([]);
      setFlatItems([]);
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
    }, 300);
  }, [doSearch]);

  // Handle input change - detect @ mentions
  const handleInputChange = useCallback((text: string, cursorPosition: number) => {
    textRef.current = text;

    // Don't show dropdown if agent already selected
    if (selectedAgent) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // Find if we're in a mention context (@ before cursor)
    const textBeforeCursor = text.slice(0, cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex === -1) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // Check if @ is at start or after a space (not in middle of word)
    const charBeforeAt = lastAtIndex > 0 ? text[lastAtIndex - 1] : ' ';
    if (charBeforeAt !== ' ' && charBeforeAt !== '\n' && lastAtIndex !== 0) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // Check if there's a space after the query (mention completed)
    const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1);
    if (textAfterAt.includes(' ')) {
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return;
    }

    // We're in a mention context
    const query = textAfterAt;
    setMentionState({
      isOpen: true,
      query,
      startIndex: lastAtIndex,
    });

    searchDebounced(query);
  }, [searchDebounced, selectedAgent]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent): boolean => {
    if (!mentionState.isOpen || flatItems.length === 0) {
      return false;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, flatItems.length - 1));
        return true;

      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
        return true;

      case 'Enter':
      case 'Tab':
        if (flatItems[selectedIndex]) {
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
  }, [mentionState.isOpen, flatItems, selectedIndex]);

  // Handle selection
  const handleSelect = useCallback((item: MentionItem): string => {
    const text = textRef.current;
    const { startIndex, query } = mentionState;

    if (item.type === 'contact') {
      // Insert @ContactName into text
      const before = text.slice(0, startIndex);
      const after = text.slice(startIndex + 1 + query.length);
      const newText = `${before}@${item.name} ${after}`;

      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return newText;
    } else {
      // Agent: remove @query from text, set agent pill
      const before = text.slice(0, startIndex);
      const after = text.slice(startIndex + 1 + query.length);
      const newText = `${before}${after}`.trim();

      setSelectedAgent(item.agent!);
      setMentionState({ isOpen: false, query: '', startIndex: -1 });
      return newText;
    }
  }, [mentionState]);

  // Close dropdown
  const handleClose = useCallback(() => {
    setMentionState({ isOpen: false, query: '', startIndex: -1 });
  }, []);

  // Remove selected agent
  const removeAgent = useCallback(() => {
    setSelectedAgent(null);
  }, []);

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  return {
    sections,
    flatItems,
    isLoading,
    selectedIndex,
    isOpen: mentionState.isOpen,
    selectedAgent,
    handleInputChange,
    handleKeyDown,
    handleSelect,
    handleClose,
    removeAgent,
  };
}
