'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  listAgents,
  getAgent as getAgentApi,
  registerAgent as registerAgentApi,
  updateAgent as updateAgentApi,
  deleteAgent as deleteAgentApi,
  generateAgent as generateAgentApi,
} from '../services/agentApi';
import type { GenerateProgressEvent } from '../services/agentApi';
import type {
  AgentSpec,
  AgentListResponse,
  RegisterAgentRequest,
  UpdateAgentRequest,
} from '../types/agent';

/**
 * useAgents - Hook for fetching the list of agents from the registry.
 *
 * Usage:
 * ```tsx
 * const { agents, total, isLoading, error, refetch } = useAgents();
 * ```
 */
export function useAgents(
  category?: string,
  tags?: string[],
  activeOnly: boolean = false,
  includeSystem: boolean = true
) {
  const [data, setData] = useState<AgentListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await listAgents(category, tags, activeOnly, includeSystem);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch agents'));
    } finally {
      setIsLoading(false);
    }
  }, [category, tags, activeOnly, includeSystem]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return {
    agents: data?.agents || [],
    count: data?.count || 0,
    isLoading,
    error,
    refetch,
  };
}

/**
 * useAgent - Hook for fetching a single agent by name.
 *
 * Usage:
 * ```tsx
 * const { agent, isLoading, error, refetch } = useAgent('my-agent');
 * ```
 */
export function useAgent(name: string | null, version?: string) {
  const [agent, setAgent] = useState<AgentSpec | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    if (!name) {
      setAgent(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await getAgentApi(name, version);
      setAgent(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch agent'));
    } finally {
      setIsLoading(false);
    }
  }, [name, version]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { agent, isLoading, error, refetch };
}

/**
 * useRegisterAgent - Hook for registering a new agent.
 *
 * Usage:
 * ```tsx
 * const { register, isLoading, error } = useRegisterAgent();
 * await register({ name: 'my-agent', yaml_content: '...' });
 * ```
 */
export function useRegisterAgent() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const register = useCallback(async (request: RegisterAgentRequest): Promise<AgentSpec> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await registerAgentApi(request);
      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to register agent');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { register, isLoading, error };
}

/**
 * useUpdateAgent - Hook for updating an existing agent.
 *
 * Usage:
 * ```tsx
 * const { update, isLoading, error } = useUpdateAgent();
 * await update(agentId, { yaml_content: '...' });
 * ```
 */
export function useUpdateAgent() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const update = useCallback(
    async (specId: string, request: UpdateAgentRequest): Promise<AgentSpec> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await updateAgentApi(specId, request);
        return result;
      } catch (e) {
        const err = e instanceof Error ? e : new Error('Failed to update agent');
        setError(err);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  return { update, isLoading, error };
}

/**
 * useDeleteAgent - Hook for deleting an agent.
 *
 * Usage:
 * ```tsx
 * const { deleteAgent, isLoading, error } = useDeleteAgent();
 * await deleteAgent(agentId);
 * ```
 */
export function useDeleteAgent() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const remove = useCallback(async (specId: string, reason?: string): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      await deleteAgentApi(specId, reason);
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to delete agent');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { deleteAgent: remove, isLoading, error };
}

// ============================================
// Agent Generation Hook (SSE streaming)
// ============================================

/**
 * useGenerateAgent - Hook for AI-powered agent generation with SSE progress.
 *
 * Sends a description, streams progress events (ideating → generating → registering),
 * and returns the registered agent on completion.
 */
export function useGenerateAgent() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [progress, setProgress] = useState<{ phase: string; message: string } | null>(null);

  const generate = useCallback(async (description: string, context?: string): Promise<GenerateProgressEvent> => {
    setIsLoading(true);
    setError(null);
    setProgress(null);
    try {
      const result = await generateAgentApi(description, context, (phase, message) => {
        setProgress({ phase, message });
      });
      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to generate agent');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
      setProgress(null);
    }
  }, []);

  return { generate, isLoading, progress, error };
}
