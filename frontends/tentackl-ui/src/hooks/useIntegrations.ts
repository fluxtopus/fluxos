'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  listIntegrations,
  getIntegration as getIntegrationApi,
  createIntegration as createIntegrationApi,
  updateIntegration as updateIntegrationApi,
  deleteIntegration as deleteIntegrationApi,
} from '../services/integrationApi';
import type {
  Integration,
  IntegrationListResponse,
  CreateIntegrationRequest,
  UpdateIntegrationRequest,
  IntegrationProvider,
  IntegrationDirection,
  IntegrationStatus,
} from '../types/integration';

/**
 * useIntegrations - Hook for fetching the list of integrations.
 *
 * Supports filtering by provider, direction, and status.
 *
 * Usage:
 * ```tsx
 * const { integrations, total, isLoading, error, refetch } = useIntegrations();
 * // With filters
 * const { integrations } = useIntegrations('discord', 'outbound', 'active');
 * ```
 */
export function useIntegrations(
  provider?: IntegrationProvider,
  direction?: IntegrationDirection,
  status?: IntegrationStatus,
) {
  const [data, setData] = useState<IntegrationListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await listIntegrations(provider, direction, status);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch integrations'));
    } finally {
      setIsLoading(false);
    }
  }, [provider, direction, status]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return {
    integrations: data?.items || [],
    total: data?.total || 0,
    isLoading,
    error,
    refetch,
  };
}

/**
 * useIntegration - Hook for fetching a single integration by ID.
 *
 * Usage:
 * ```tsx
 * const { integration, isLoading, error, refetch } = useIntegration('int-123');
 * ```
 */
export function useIntegration(integrationId: string | null) {
  const [integration, setIntegration] = useState<Integration | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(async () => {
    if (!integrationId) {
      setIntegration(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const result = await getIntegrationApi(integrationId);
      setIntegration(result);
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to fetch integration'));
    } finally {
      setIsLoading(false);
    }
  }, [integrationId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { integration, isLoading, error, refetch };
}

/**
 * useCreateIntegration - Hook for creating a new integration.
 *
 * Usage:
 * ```tsx
 * const { create, isLoading, error } = useCreateIntegration();
 * await create({ name: 'My Discord', provider: 'discord' });
 * ```
 */
export function useCreateIntegration() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const create = useCallback(async (request: CreateIntegrationRequest): Promise<Integration> => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await createIntegrationApi(request);
      return result;
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to create integration');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { create, isLoading, error };
}

/**
 * useUpdateIntegration - Hook for updating an existing integration.
 *
 * Usage:
 * ```tsx
 * const { update, isLoading, error } = useUpdateIntegration();
 * await update('int-123', { status: 'paused' });
 * ```
 */
export function useUpdateIntegration() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const update = useCallback(
    async (integrationId: string, request: UpdateIntegrationRequest): Promise<Integration> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await updateIntegrationApi(integrationId, request);
        return result;
      } catch (e) {
        const err = e instanceof Error ? e : new Error('Failed to update integration');
        setError(err);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { update, isLoading, error };
}

/**
 * useDeleteIntegration - Hook for deleting an integration.
 *
 * Usage:
 * ```tsx
 * const { deleteIntegration, isLoading, error } = useDeleteIntegration();
 * await deleteIntegration('int-123');
 * ```
 */
export function useDeleteIntegration() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const remove = useCallback(async (integrationId: string): Promise<void> => {
    setIsLoading(true);
    setError(null);
    try {
      await deleteIntegrationApi(integrationId);
    } catch (e) {
      const err = e instanceof Error ? e : new Error('Failed to delete integration');
      setError(err);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { deleteIntegration: remove, isLoading, error };
}
