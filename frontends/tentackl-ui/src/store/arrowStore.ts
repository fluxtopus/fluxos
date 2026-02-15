import { create } from 'zustand';
import type { ConversationSummary, WorkflowSpec, WorkflowRun } from '../services/arrow';
import { listConversations, getConversationSpecs, getSpecRuns } from '../services/arrow';

interface ArrowState {
  // Selection state
  selectedConversationId: string | null;
  selectedSpecId: string | null;

  // Data
  conversations: ConversationSummary[];
  specs: WorkflowSpec[];
  runs: Record<string, WorkflowRun[]>; // Keyed by spec_id

  // Loading states
  loadingConversations: boolean;
  loadingSpecs: boolean;
  loadingRuns: Record<string, boolean>;

  // Actions
  setSelectedConversation: (id: string | null) => void;
  setSelectedSpec: (id: string | null) => void;
  loadConversations: () => Promise<void>;
  loadSpecs: (conversationId: string) => Promise<void>;
  loadRuns: (specId: string) => Promise<void>;
  refreshConversations: () => Promise<void>;
  clearSelection: () => void;
}

export const useArrowStore = create<ArrowState>((set, get) => ({
  // Initial state
  selectedConversationId: null,
  selectedSpecId: null,
  conversations: [],
  specs: [],
  runs: {},
  loadingConversations: false,
  loadingSpecs: false,
  loadingRuns: {},

  // Actions
  setSelectedConversation: (id) => {
    set({
      selectedConversationId: id,
      selectedSpecId: null, // Clear spec selection when changing conversations
      specs: [],
      runs: {}
    });

    // Auto-load specs when conversation is selected
    if (id) {
      get().loadSpecs(id);
    }
  },

  setSelectedSpec: (id) => {
    set({ selectedSpecId: id });

    // Auto-load runs when spec is selected
    if (id) {
      get().loadRuns(id);
    }
  },

  loadConversations: async () => {
    set({ loadingConversations: true });
    try {
      const conversations = await listConversations();
      set({ conversations });
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      set({ loadingConversations: false });
    }
  },

  loadSpecs: async (conversationId) => {
    set({ loadingSpecs: true });
    try {
      const specs = await getConversationSpecs(conversationId);
      set({ specs });
    } catch (error) {
      console.error('Failed to load specs:', error);
      set({ specs: [] });
    } finally {
      set({ loadingSpecs: false });
    }
  },

  loadRuns: async (specId) => {
    set((state) => ({
      loadingRuns: { ...state.loadingRuns, [specId]: true }
    }));

    try {
      const runs = await getSpecRuns(specId);
      set((state) => ({
        runs: { ...state.runs, [specId]: runs }
      }));
    } catch (error) {
      console.error('Failed to load runs:', error);
    } finally {
      set((state) => ({
        loadingRuns: { ...state.loadingRuns, [specId]: false }
      }));
    }
  },

  refreshConversations: async () => {
    await get().loadConversations();
  },

  clearSelection: () => {
    set({
      selectedConversationId: null,
      selectedSpecId: null,
      specs: [],
      runs: {}
    });
  }
}));
