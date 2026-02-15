import { useCallback } from 'react';
import { useAuthStore, PendingAction } from '../store/authStore';

/**
 * Hook to guard actions that require authentication
 *
 * Usage:
 * const { requireAuth, isAuthenticated } = useAuthGuard();
 *
 * // Gate an action
 * const handleSave = () => {
 *   requireAuth(() => {
 *     // This only runs if authenticated
 *     saveWorkflow();
 *   }, 'save', 'Save your workflow');
 * };
 */
export function useAuthGuard() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const openAuthModal = useAuthStore((state) => state.openAuthModal);

  /**
   * Require authentication before executing an action
   * If not authenticated, shows auth modal and stores action for later
   *
   * @param action - Function to execute if authenticated
   * @param type - Type of action (save, share, copy, edit)
   * @param description - Optional description for the modal
   */
  const requireAuth = useCallback(
    (
      action: () => void | Promise<void>,
      type: PendingAction['type'],
      description?: string
    ) => {
      if (isAuthenticated) {
        // User is authenticated, execute action immediately
        action();
      } else {
        // User is not authenticated, show modal with pending action
        openAuthModal('register', {
          type,
          callback: action,
          description,
        });
      }
    },
    [isAuthenticated, openAuthModal]
  );

  /**
   * Check if authenticated without triggering modal
   * Useful for conditional rendering
   */
  const checkAuth = useCallback(() => {
    return isAuthenticated;
  }, [isAuthenticated]);

  return {
    requireAuth,
    checkAuth,
    isAuthenticated,
  };
}
