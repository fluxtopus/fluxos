'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  listCapabilities as listCapabilitiesApi,
  searchCapabilities as searchCapabilitiesApi,
  getCapability as getCapabilityApi,
  createCapability as createCapabilityApi,
  deleteCapability as deleteCapabilityApi,
  updateCapability as updateCapabilityApi,
} from '../services/capabilityApi';
import type {
  Capability,
  CapabilityDetail,
  CapabilitiesListResponse,
  CapabilitiesSearchResponse,
  CapabilityListFilters,
  CapabilitySearchFilters,
  CreateCapabilityRequest,
  UpdateCapabilityRequest,
  UpdateCapabilityResponse,
} from '../types/capability';

/**
 * useCapabilities - Hook for fetching the list of capabilities.
 *
 * Usage:
 * ```tsx
 * const { capabilities, total, isLoading, error, refetch } = useCapabilities();
 * ```
 */
export function useCapabilities(filters: CapabilityListFilters = {}) {
  const [data, setData] = useState<CapabilitiesListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await listCapabilitiesApi(filters);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch capabilities'));
    } finally {
      setIsLoading(false);
    }
  }, [
    filters.domain,
    filters.tags?.join(','),
    filters.include_system,
    filters.active_only,
    filters.limit,
    filters.offset,
  ]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return {
    capabilities: data?.capabilities || [],
    count: data?.count || 0,
    total: data?.total || 0,
    isLoading,
    error,
    refetch,
  };
}

/**
 * useCapabilitySearch - Hook for searching capabilities.
 *
 * Usage:
 * ```tsx
 * const { search, results, isLoading, error } = useCapabilitySearch();
 * await search({ query: 'summarize' });
 * ```
 */
export function useCapabilitySearch() {
  const [data, setData] = useState<CapabilitiesSearchResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const search = useCallback(async (filters: CapabilitySearchFilters) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await searchCapabilitiesApi(filters);
      setData(result);
      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to search capabilities');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return {
    search,
    results: data?.results || [],
    count: data?.count || 0,
    searchType: data?.search_type,
    query: data?.query,
    isLoading,
    error,
    reset,
  };
}

/**
 * useCapability - Hook for fetching a single capability by ID.
 *
 * Usage:
 * ```tsx
 * const { capability, isLoading, error, refetch } = useCapability('uuid-here');
 * ```
 */
export function useCapability(id: string | null) {
  const [capability, setCapability] = useState<CapabilityDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    if (!id) {
      setCapability(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await getCapabilityApi(id);
      setCapability(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch capability'));
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { capability, isLoading, error, refetch };
}

/**
 * useCreateCapability - Hook for creating a new capability.
 *
 * Usage:
 * ```tsx
 * const { create, isLoading, error } = useCreateCapability();
 * await create({ spec_yaml: '...' });
 * ```
 */
export function useCreateCapability() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const create = useCallback(async (request: CreateCapabilityRequest): Promise<CapabilityDetail> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await createCapabilityApi(request);
      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to create capability');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { create, isLoading, error };
}

/**
 * useUpdateCapability - Hook for updating an existing capability.
 *
 * Usage:
 * ```tsx
 * const { update, isLoading, error } = useUpdateCapability();
 * await update(id, { tags: ['new-tag'] });
 * ```
 */
export function useUpdateCapability() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const update = useCallback(
    async (id: string, request: UpdateCapabilityRequest): Promise<UpdateCapabilityResponse> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await updateCapabilityApi(id, request);
        return result;
      } catch (e) {
        const err = e instanceof Error ? e : new Error('Failed to update capability');
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
 * useDeleteCapability - Hook for deleting a capability.
 *
 * Usage:
 * ```tsx
 * const { deleteCapability, isLoading, error } = useDeleteCapability();
 * await deleteCapability(id);
 * ```
 */
export function useDeleteCapability() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const remove = useCallback(async (id: string): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      await deleteCapabilityApi(id);
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to delete capability');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { deleteCapability: remove, isLoading, error };
}
