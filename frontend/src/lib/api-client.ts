import axios from 'axios';

function resolveApiUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) {
    // Accept either http://host or http://host/api/v1 and normalize to origin.
    return configured.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
  }

  // Keep frontend calls pinned to backend API host in local dev.
  return 'http://127.0.0.1:8000';
}

const API_URL = resolveApiUrl();

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
