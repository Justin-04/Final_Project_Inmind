export type Role = 'user' | 'admin';

export interface AuthState {
  access_token: string;
  role: Role;
  username: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  telemetry?: ChatTelemetry;
  createdAt: number;
}

export interface ChatTelemetry {
  intent: 'rag' | 'diagnostic' | 'pricing';
  confidence: number;
  route: string;
  iterations: number;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  intent?: string;
  metadata?: {
    confidence?: number;
    route?: string;
    iteration_count?: number;
  };
}

export interface KnowledgeDocument {
  source: string;
  drone_model: string;
  chunk_count: number;
}

const AUTH_KEY = 'dji_auth';

export function getAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthState;
  } catch {
    return null;
  }
}

export function setAuth(state: AuthState) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(state));
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const auth = getAuth();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (auth?.access_token) {
    headers['Authorization'] = `Bearer ${auth.access_token}`;
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    clearAuth();
    onUnauthorized?.();
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail || body.message || detail;
    } catch {
      /* ignore parse error */
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

export const api = {
  register(username: string, password: string, role: Role) {
    return request<AuthResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, role }),
    });
  },

  login(username: string, password: string) {
    return request<AuthResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  chat(query: string, userId: string, conversationId: string | null) {
    return request<ChatResponse>('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify({
        query,
        user_id: userId,
        conversation_id: conversationId,
      }),
    });
  },

  getDocuments() {
    return request<{ documents: KnowledgeDocument[] }>('/api/v1/admin/documents');
  },

  ingest(pdfBase64: string, droneModel: string, sourceName: string) {
    return request<{ status: string; result?: any; message?: string }>('/api/v1/admin/ingest', {
      method: 'POST',
      body: JSON.stringify({
        pdf_file: pdfBase64,
        drone_model: droneModel,
        source_name: sourceName,
      }),
    });
  },

  deleteDocument(sourceName: string) {
    return request<{ deleted: boolean; source: string; message: string }>(`/api/v1/admin/documents/${encodeURIComponent(sourceName)}`, {
      method: 'DELETE',
    });
  },
};

interface AuthResponse {
  access_token: string;
  token_type: string;
  role: Role;
  username: string;
}
