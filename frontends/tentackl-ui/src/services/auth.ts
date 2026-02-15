import api from './api';
import { User, useAuthStore } from '../store/authStore';
import { posthog } from '../lib/posthog';
import { AxiosError } from 'axios';

/**
 * Detect network-level errors (server down, timeout, DNS failure)
 * vs application-level errors (401, 403, etc.)
 * Network errors should NOT invalidate stored tokens.
 */
function isNetworkError(error: unknown): boolean {
  if (error instanceof AxiosError) {
    // No response at all = network failure (server unreachable, timeout, etc.)
    if (!error.response) return true;
    // 502/503/504 = server is starting up or temporarily unavailable
    const status = error.response.status;
    if (status === 502 || status === 503 || status === 504) return true;
  }
  // fetch API or other non-axios errors with no response
  if (error instanceof TypeError && error.message.includes('fetch')) return true;
  return false;
}

// Response types
interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
}

interface RegisterResponse {
  user_id: string;
  email: string;
  organization_id: string;
  status: string;
  message?: string;
}

interface VerifyEmailResponse {
  message: string;
}

interface ResendVerificationResponse {
  message: string;
}

interface UserResponse {
  id: string;
  email: string;
  username?: string;
  first_name?: string;
  last_name?: string;
  organization_id?: string;
}

// Auth API service
export const authApi = {
  /**
   * Login with email and password
   * Returns access token and refresh token on success
   */
  login: async (email: string, password: string): Promise<TokenResponse> => {
    // Backend expects 'username' field (email is used as username)
    const response = await api.post<TokenResponse>('/api/auth/token', {
      username: email,
      password,
    });
    return response.data;
  },

  /**
   * Register a new user
   */
  register: async (
    email: string,
    password: string,
    firstName?: string,
    lastName?: string,
    organizationName?: string
  ): Promise<RegisterResponse> => {
    const response = await api.post<RegisterResponse>('/api/auth/register', {
      email,
      password,
      ...(firstName && { first_name: firstName }),
      ...(lastName && { last_name: lastName }),
      ...(organizationName && { organization_name: organizationName }),
    });
    return response.data;
  },

  /**
   * Get current user info
   * Requires valid auth token
   */
  getCurrentUser: async (): Promise<UserResponse> => {
    const response = await api.get<UserResponse>('/api/auth/me');
    return response.data;
  },

  /**
   * Verify email with OTP code
   */
  verifyEmail: async (email: string, code: string): Promise<VerifyEmailResponse> => {
    const response = await api.post<VerifyEmailResponse>('/api/auth/verify-email', {
      email,
      code,
    });
    return response.data;
  },

  /**
   * Resend verification email
   */
  resendVerification: async (email: string): Promise<ResendVerificationResponse> => {
    const response = await api.post<ResendVerificationResponse>('/api/auth/resend-verification', {
      email,
    });
    return response.data;
  },

  /**
   * Validate stored token and get user
   * Returns user if valid, null if invalid
   * Throws on network errors so callers can distinguish from invalid tokens
   */
  validateToken: async (): Promise<User | null> => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      return null;
    }

    try {
      const user = await authApi.getCurrentUser();
      return {
        id: user.id,
        email: user.email,
        username: user.username,
        first_name: user.first_name,
        last_name: user.last_name,
        organization_id: user.organization_id,
      };
    } catch (error: unknown) {
      // Distinguish network errors from actual auth failures
      // Network errors (server down, timeout) should NOT clear tokens
      if (isNetworkError(error)) {
        console.warn('Network error during token validation - keeping tokens for retry');
        throw error; // Re-throw so callers know this wasn't an auth rejection
      }
      // 401 = token is genuinely invalid, clear it
      localStorage.removeItem('auth_token');
      return null;
    }
  },
};

/**
 * Initialize auth state on app load
 * Checks for existing token and validates it
 * Restores refresh token for session persistence
 */
export async function initializeAuth(): Promise<void> {
  const { setUser, setToken, setRefreshToken, setLoading, setInitialized, refreshAccessToken } = useAuthStore.getState();

  setLoading(true);

  try {
    const token = localStorage.getItem('auth_token');
    const refreshToken = localStorage.getItem('refresh_token');

    // Restore refresh token from localStorage
    if (refreshToken) {
      setRefreshToken(refreshToken);
    }

    if (token) {
      try {
        const user = await authApi.validateToken();
        if (user) {
          setToken(token);
          setUser(user);
          // Identify user in PostHog
          posthog.identify(user.id, {
            email: user.email,
            organization_id: user.organization_id,
          });
        } else {
          // Access token invalid (got a 401) - try refresh if we have a refresh token
          if (refreshToken) {
            const refreshed = await refreshAccessToken();
            if (refreshed) {
              // Token refreshed, try again to get user
              try {
                const refreshedUser = await authApi.validateToken();
                if (refreshedUser) {
                  setUser(refreshedUser);
                  posthog.identify(refreshedUser.id, {
                    email: refreshedUser.email,
                    organization_id: refreshedUser.organization_id,
                  });
                }
              } catch {
                // Network error after refresh - keep tokens, user will retry
                console.warn('Network error after token refresh - keeping session');
              }
            }
          } else {
            setToken(null);
            setUser(null);
          }
        }
      } catch (error) {
        // validateToken throws on network errors - keep tokens intact
        if (isNetworkError(error)) {
          console.warn('Server unreachable during auth init - preserving session for retry');
          // Restore token and user from persisted store so the app stays "logged in"
          // The next API call will re-attempt validation via the interceptor
          setToken(token);
        } else {
          throw error;
        }
      }
    }
  } catch (error) {
    console.error('Auth initialization failed:', error);
    // Only clear auth on non-network errors (unexpected failures)
    if (!isNetworkError(error)) {
      setToken(null);
      setUser(null);
    }
  } finally {
    setLoading(false);
    setInitialized(true);
  }
}

/**
 * Login flow - authenticates and stores token/user
 */
export async function loginUser(email: string, password: string): Promise<User> {
  const { login } = useAuthStore.getState();

  // Get token (includes refresh_token for session persistence)
  const tokenResponse = await authApi.login(email, password);

  // Store token temporarily to make the getCurrentUser call
  localStorage.setItem('auth_token', tokenResponse.access_token);

  // Get user info
  const userResponse = await authApi.getCurrentUser();

  const user: User = {
    id: userResponse.id,
    email: userResponse.email,
    username: userResponse.username,
    first_name: userResponse.first_name,
    last_name: userResponse.last_name,
    organization_id: userResponse.organization_id,
  };

  // Update store with both access token and refresh token
  login(tokenResponse.access_token, user, tokenResponse.refresh_token);

  // Identify user in PostHog
  posthog.identify(user.id, {
    email: user.email,
    organization_id: user.organization_id,
  });

  return user;
}

/**
 * Register flow - creates account and returns registration response
 * User must verify email before logging in
 */
export async function registerUser(
  email: string,
  password: string,
  firstName?: string,
  lastName?: string,
  organizationName?: string
): Promise<RegisterResponse> {
  // Register - returns pending status, user must verify email
  const response = await authApi.register(email, password, firstName, lastName, organizationName);
  return response;
}

/**
 * Verify email with OTP code
 */
export async function verifyEmail(email: string, code: string): Promise<void> {
  await authApi.verifyEmail(email, code);
}

/**
 * Resend verification email
 */
export async function resendVerification(email: string): Promise<void> {
  await authApi.resendVerification(email);
}

/**
 * Logout flow - clears token and user
 */
export function logoutUser(): void {
  const { logout } = useAuthStore.getState();
  logout();
  // Reset PostHog user identification
  posthog.reset();
}

// Additional API methods for account settings
export const accountApi = {
  updateProfile: async (data: { first_name?: string; last_name?: string }) => {
    const response = await api.patch('/api/auth/profile', data);
    return response.data;
  },

  initiateEmailChange: async (newEmail: string) => {
    const response = await api.post('/api/auth/email-change/initiate', {
      new_email: newEmail,
    });
    return response.data;
  },

  confirmEmailChange: async (code: string) => {
    const response = await api.post('/api/auth/email-change/confirm', { code });
    return response.data;
  },

  forgotPassword: async (email: string) => {
    const response = await api.post('/api/auth/forgot-password', { email });
    return response.data;
  },

  resetPassword: async (email: string, code: string, newPassword: string) => {
    const response = await api.post('/api/auth/reset-password', {
      email,
      code,
      new_password: newPassword,
    });
    return response.data;
  },

  getOrganization: async (orgId: string) => {
    const response = await api.get(`/api/organizations/${orgId}`);
    return response.data;
  },

  updateOrganization: async (orgId: string, data: { name?: string }) => {
    const response = await api.patch(`/api/organizations/${orgId}`, data);
    return response.data;
  },
};

export default authApi;
