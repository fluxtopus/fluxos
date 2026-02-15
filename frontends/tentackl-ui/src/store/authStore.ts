import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

// Types
export interface User {
  id: string;
  email: string;
  username?: string;
  first_name?: string;
  last_name?: string;
  organization_id?: string;
}

export interface PendingAction {
  type: 'save' | 'share' | 'copy' | 'edit';
  callback?: () => void | Promise<void>;
  description?: string;
}

interface AuthStore {
  // State
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;

  // Auth modal state
  showAuthModal: boolean;
  authModalTab: 'login' | 'register';
  pendingAction: PendingAction | null;

  // Actions
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  setRefreshToken: (refreshToken: string | null) => void;
  setLoading: (loading: boolean) => void;
  setInitialized: (initialized: boolean) => void;

  // Auth modal actions
  openAuthModal: (tab?: 'login' | 'register', action?: PendingAction) => void;
  closeAuthModal: () => void;
  setAuthModalTab: (tab: 'login' | 'register') => void;
  setPendingAction: (action: PendingAction | null) => void;
  executePendingAction: () => Promise<void>;

  // Auth flow actions
  login: (token: string, user: User, refreshToken?: string) => void;
  logout: () => void;
  refreshAccessToken: () => Promise<boolean>;

  // Computed
  checkIsAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        user: null,
        token: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        isInitialized: false,

        // Auth modal state
        showAuthModal: false,
        authModalTab: 'login',
        pendingAction: null,

        // Basic setters
        setUser: (user) => set({ user, isAuthenticated: !!user }),
        setToken: (token) => {
          if (token) {
            localStorage.setItem('auth_token', token);
          } else {
            localStorage.removeItem('auth_token');
          }
          set({ token });
        },
        setRefreshToken: (refreshToken) => {
          if (refreshToken) {
            localStorage.setItem('refresh_token', refreshToken);
          } else {
            localStorage.removeItem('refresh_token');
          }
          set({ refreshToken });
        },
        setLoading: (isLoading) => set({ isLoading }),
        setInitialized: (isInitialized) => set({ isInitialized }),

        // Auth modal actions
        openAuthModal: (tab = 'login', action) => {
          set({
            showAuthModal: true,
            authModalTab: tab,
            pendingAction: action ?? null
          });
        },

        closeAuthModal: () => {
          set({
            showAuthModal: false,
            pendingAction: null
          });
        },

        setAuthModalTab: (tab) => set({ authModalTab: tab }),

        setPendingAction: (action) => set({ pendingAction: action }),

        executePendingAction: async () => {
          const { pendingAction } = get();
          if (pendingAction?.callback) {
            try {
              await pendingAction.callback();
            } catch (error) {
              console.error('Failed to execute pending action:', error);
            }
          }
          set({ pendingAction: null });
        },

        // Auth flow
        login: (token, user, refreshToken) => {
          localStorage.setItem('auth_token', token);
          if (refreshToken) {
            localStorage.setItem('refresh_token', refreshToken);
          }
          set({
            token,
            user,
            refreshToken: refreshToken ?? null,
            isAuthenticated: true,
            showAuthModal: false
          });

          // Execute pending action after login
          const { pendingAction } = get();
          if (pendingAction?.callback) {
            // Small delay to let UI update
            setTimeout(() => {
              get().executePendingAction();
            }, 100);
          }
        },

        logout: () => {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('refresh_token');
          set({
            token: null,
            refreshToken: null,
            user: null,
            isAuthenticated: false
          });
        },

        refreshAccessToken: async () => {
          let { refreshToken } = get();

          // Fallback to localStorage if store hasn't hydrated yet
          // This handles race conditions where API calls happen before Zustand rehydration
          if (!refreshToken && typeof window !== 'undefined') {
            refreshToken = localStorage.getItem('refresh_token');
            if (refreshToken) {
              // Update store for consistency
              set({ refreshToken });
            }
          }

          if (!refreshToken) {
            console.debug('No refresh token available');
            return false;
          }

          try {
            // Use the same direct API URL as the axios instance so the
            // request goes straight to Tentackl instead of through the
            // Next.js server-side proxy (which can't reach the backend
            // from inside the Docker container).
            const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';
            const response = await fetch(`${baseUrl}/api/auth/refresh?refresh_token=${encodeURIComponent(refreshToken)}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
            });

            if (!response.ok) {
              // 502/503/504 = server is down or restarting, keep tokens
              if (response.status >= 502 && response.status <= 504) {
                console.warn('Server unavailable during token refresh - keeping session');
                return false;
              }
              // 401/403 = token is genuinely invalid
              get().logout();
              return false;
            }

            const data = await response.json();
            const newToken = data.access_token;
            // Backend doesn't return new refresh token, reuse existing
            // (refresh tokens have 7-day expiry vs 30 min for access tokens)

            // Update access token
            localStorage.setItem('auth_token', newToken);

            set({
              token: newToken,
            });

            console.debug('Token refreshed successfully');
            return true;
          } catch (error) {
            // Network errors (TypeError: Failed to fetch) = server unreachable
            // Don't destroy the session - user can retry when server is back
            if (error instanceof TypeError) {
              console.warn('Network error during token refresh - keeping session');
              return false;
            }
            console.error('Token refresh failed:', error);
            get().logout();
            return false;
          }
        },

        // Computed
        checkIsAuthenticated: () => {
          const { token, user } = get();
          return !!token && !!user;
        },
      }),
      {
        name: 'auth-store',
        partialize: (state) => ({
          // Only persist these fields
          token: state.token,
          refreshToken: state.refreshToken,
          user: state.user,
          isAuthenticated: state.isAuthenticated,
        }),
        // Validate hydrated state to prevent crashes from corrupted localStorage
        onRehydrateStorage: () => (state) => {
          if (state?.user && !state.user.email) {
            // Clear invalid user state
            state.user = null;
            state.token = null;
            state.isAuthenticated = false;
            localStorage.removeItem('auth_token');
          }
        },
      }
    ),
    {
      name: 'auth-store',
    }
  )
);

// Expose hydration status so components can wait for localStorage restore
export const waitForAuthHydration = () => {
  return new Promise<void>((resolve) => {
    if (useAuthStore.persist.hasHydrated()) {
      resolve();
    } else {
      useAuthStore.persist.onFinishHydration(() => resolve());
    }
  });
};

// Listen for session expiry events from API interceptor (outside of store)
if (typeof window !== 'undefined') {
  window.addEventListener('auth:session-expired', () => {
    useAuthStore.getState().logout();
  });
}
