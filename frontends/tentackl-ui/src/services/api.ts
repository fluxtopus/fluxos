import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { Workflow, WorkflowSummary, WorkflowMetrics } from '../types/workflow';
import { useAuthStore } from '../store/authStore';

// Use NEXT_PUBLIC_API_URL for direct API calls (avoids proxy timeout issues on long requests)
// Falls back to empty string to use Next.js proxy for backward compatibility
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Track if we're currently refreshing to prevent infinite loops
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (value?: unknown) => void;
  reject: (reason?: unknown) => void;
  config: InternalAxiosRequestConfig;
}> = [];

const processQueue = (error: Error | null, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject, config }) => {
    if (error) {
      reject(error);
    } else if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      resolve(api(config));
    }
  });
  failedQueue = [];
};

// Add auth token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses - try token refresh before logging out
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    // Network errors (no response) = server is down, don't touch auth state
    if (!error.response) {
      return Promise.reject(error);
    }

    // 502/503/504 = server starting up, don't touch auth state
    if (error.response.status >= 502 && error.response.status <= 504) {
      return Promise.reject(error);
    }

    // Only handle 401 errors that aren't from the refresh endpoint itself
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't retry refresh requests
      if (originalRequest.url?.includes('/auth/refresh')) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue this request to be retried after token refresh
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject, config: originalRequest });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        // Attempt token refresh
        const refreshed = await useAuthStore.getState().refreshAccessToken();

        if (refreshed) {
          const newToken = localStorage.getItem('auth_token');
          processQueue(null, newToken);

          // Retry the original request with new token
          if (newToken) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
          }
          return api(originalRequest);
        } else {
          // Refresh failed - clear auth only if it was an actual 401, not a network error
          processQueue(new Error('Token refresh failed'));
          window.dispatchEvent(new CustomEvent('auth:session-expired'));
          return Promise.reject(error);
        }
      } catch (refreshError) {
        // Don't expire session on network errors during refresh
        const isNetwork = refreshError instanceof AxiosError && !refreshError.response;
        if (!isNetwork) {
          processQueue(refreshError as Error);
          window.dispatchEvent(new CustomEvent('auth:session-expired'));
        } else {
          processQueue(refreshError as Error);
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const workflowApi = {
  // Get all workflow runs (legacy endpoint name, actually returns runs)
  listWorkflows: async (): Promise<WorkflowSummary[]> => {
    const response = await api.get<{ workflows: WorkflowSummary[] }>('/api/workflows');
    return response.data.workflows;
  },

  // Get workflow run visualization data (nodes, edges, execution tree)
  getWorkflow: async (workflowId: string): Promise<Workflow> => {
    const response = await api.get<Workflow>(`/api/workflow-runs/${workflowId}/visualization`);
    return response.data;
  },

  // Get workflow run metrics
  getWorkflowMetrics: async (workflowId: string): Promise<WorkflowMetrics> => {
    const response = await api.get<WorkflowMetrics>(`/api/workflow-runs/${workflowId}/metrics`);
    return response.data;
  },

  // Replay workflow run
  replayWorkflow: async (workflowId: string): Promise<void> => {
    await api.post(`/api/workflows/${workflowId}/replay`);
  },

  // Get agent logs
  getAgentLogs: async (agentId: string, limit: number = 100): Promise<any[]> => {
    const response = await api.get(`/api/agents/${agentId}/logs`, {
      params: { limit },
    });
    return response.data.logs;
  },
};

export default api;