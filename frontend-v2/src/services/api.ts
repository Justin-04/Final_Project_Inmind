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
  cacheHit?: boolean;
}

export interface ChatResponse {
  response: string;
  conversation_id: string;
  intent?: string;
  metadata?: {
    confidence?: number;
    route?: string;
    iteration_count?: number;
    cache_hit?: boolean;
    cache_score?: number;
  };
}

export interface KnowledgeDocument {
  source: string;
  drone_model: string;
  chunk_count: number;
}

export interface FeedbackItem {
  conversation_id: string;
  message_index: number;
  rating: number;
  comment: string | null;
  user_id: string;
  created_at: string;
  flagged_message?: string;
  user_query?: string;
  total_messages?: number;
  conversation_title?: string;
}

export interface FeedbackResponse {
  feedback: FeedbackItem[];
  stats: {
    total: number;
    positive: number;
    negative: number;
    satisfaction_rate: number;
  };
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

  if (res.status === 429) {
    let retryAfter = res.headers.get('Retry-After') || '60';
    let detail = `Rate limit exceeded. Please wait ${retryAfter} seconds before trying again.`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse error */
    }
    const err = new Error(detail);
    (err as any).status = 429;
    (err as any).retryAfter = parseInt(retryAfter, 10);
    throw err;
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

  getConversations(userId: string) {
    return request<{ conversations: Array<{ conversation_id: string; created_at: string; updated_at: string }> }>(
      `/api/v1/conversations?user_id=${encodeURIComponent(userId)}`
    );
  },

  getConversation(conversationId: string) {
    return request<{ conversation_id: string; messages: Array<{ role: string; content: string; timestamp: string }> }>(
      `/api/v1/conversations/${conversationId}`
    );
  },

  renameConversation(conversationId: string, title: string) {
    return request<{ status: string; title: string }>(`/api/v1/conversations/${conversationId}/rename`, {
      method: 'PUT',
      body: JSON.stringify({ title }),
    });
  },

  deleteConversation(conversationId: string) {
    return request<{ status: string }>(`/api/v1/conversations/${conversationId}`, {
      method: 'DELETE',
    });
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

  async voiceChat(audioBlob: Blob, userId: string, conversationId: string | null) {
    const auth = getAuth();
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('user_id', userId);
    if (conversationId) formData.append('conversation_id', conversationId);

    const headers: Record<string, string> = {};
    if (auth?.access_token) {
      headers['Authorization'] = `Bearer ${auth.access_token}`;
    }

    const res = await fetch('/api/v1/voice', {
      method: 'POST',
      headers,
      body: formData,
    });

    if (res.status === 401) {
      clearAuth();
      onUnauthorized?.();
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || 'Voice request failed');
    }

    return res.json() as Promise<{
      transcription: string;
      conversation_id: string;
      response: string;
      intent: string;
      metadata: any;
    }>;
  },

  submitFeedback(conversationId: string, messageIndex: number, rating: 1 | -1, comment?: string) {
    return request<{ status: string; rating: number }>('/api/v1/feedback', {
      method: 'POST',
      body: JSON.stringify({
        conversation_id: conversationId,
        message_index: messageIndex,
        rating,
        comment,
      }),
    });
  },

  getAdminFeedback(rating?: number, limit: number = 50) {
    const params = new URLSearchParams();
    if (rating !== undefined) params.set('rating', String(rating));
    params.set('limit', String(limit));
    return request<FeedbackResponse>(`/api/v1/admin/feedback?${params.toString()}`);
  },
};

interface AuthResponse {
  access_token: string;
  token_type: string;
  role: Role;
  username: string;
}
