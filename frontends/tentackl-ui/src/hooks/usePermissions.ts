import { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { useAuthStore } from '../store/authStore';

interface PermissionCheckResult {
  has_permission: boolean;
  user_id: string;
  organization_id: string;
}

interface UsePermissionResult {
  hasPermission: boolean | null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

interface PermissionBatchResponse {
  permissions: Record<string, boolean>;
}

/**
 * Hook to check if the current user has a specific permission.
 *
 * @param resource - The resource to check (e.g., "capabilities", "agents")
 * @param action - The action to check (e.g., "manage", "view", "create")
 * @returns Object with hasPermission, isLoading, error, and refetch
 */
export function usePermission(resource: string, action: string): UsePermissionResult {
  const [hasPermission, setHasPermission] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { isAuthenticated } = useAuthStore();

  const checkPermission = useCallback(async () => {
    if (!isAuthenticated) {
      setHasPermission(false);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const { data } = await api.post<PermissionCheckResult>(
        `/api/auth/check?resource=${encodeURIComponent(resource)}&action=${encodeURIComponent(action)}`,
        {}
      );
      setHasPermission(data.has_permission);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to check permission'));
      setHasPermission(false);
    } finally {
      setIsLoading(false);
    }
  }, [resource, action, isAuthenticated]);

  useEffect(() => {
    checkPermission();
  }, [checkPermission]);

  return { hasPermission, isLoading, error, refetch: checkPermission };
}

/**
 * Hook to check multiple permissions at once.
 *
 * @param permissions - Array of [resource, action] tuples to check
 * @returns Object with permissions map, isLoading, error
 */
export function usePermissions(
  permissions: Array<[string, string]>
): {
  permissions: Record<string, boolean>;
  isLoading: boolean;
  error: Error | null;
} {
  const [permissionsMap, setPermissionsMap] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const { isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) {
      const defaultMap: Record<string, boolean> = {};
      permissions.forEach(([resource, action]) => {
        defaultMap[`${resource}:${action}`] = false;
      });
      setPermissionsMap(defaultMap);
      setIsLoading(false);
      return;
    }

    const checkAll = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const payload = {
          permissions: permissions.map(([resource, action]) => ({ resource, action })),
        };
        const { data } = await api.post<PermissionBatchResponse>('/api/auth/check-batch', payload);
        const map: Record<string, boolean> = {};
        permissions.forEach(([resource, action]) => {
          const key = `${resource}:${action}`;
          map[key] = !!data.permissions[key];
        });
        setPermissionsMap(map);
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to check permissions'));
      } finally {
        setIsLoading(false);
      }
    };

    checkAll();
  }, [permissions, isAuthenticated]);

  return { permissions: permissionsMap, isLoading, error };
}

/**
 * Convenience hook for checking if user can manage capabilities.
 */
export function useCanManageCapabilities(): UsePermissionResult {
  return usePermission('capabilities', 'manage');
}
