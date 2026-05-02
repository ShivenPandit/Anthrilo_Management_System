import axios from 'axios';

/** Backend origin without `/api/v1` (use for CSV download URLs, etc.). */
export function getApiOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
  }
  return 'http://127.0.0.1:8000';
}

const API_URL = getApiOrigin();

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 720000, // 12 min — generous for heavy date-range exports
});

// Attach the auth token to every outgoing request
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Global error handling (auto-logout on 401, friendly timeout message)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Kick the user back to login on 401
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    } else if (error.code === 'ECONNABORTED') {
      // Make timeout errors more readable
      error.message = 'Request timed out. The server is taking too long to respond. Please try again.';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
