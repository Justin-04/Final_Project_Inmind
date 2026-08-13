import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Loader2 } from 'lucide-react';
import { useAuth } from '@/hooks/use-auth';
import { api, type ChatMessage, type ChatTelemetry } from '@/services/api';
import { toast } from 'sonner';
import { Textarea } from '@/components/ui/textarea';
import ChatSidebar, { type ConversationMeta } from '@/components/chat/ChatSidebar';
import MessageBubble from '@/components/chat/MessageBubble';
import ThinkingIndicator from '@/components/chat/ThinkingIndicator';

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function parseIntent(intent?: string): ChatTelemetry['intent'] {
  if (intent === 'diagnostic') return 'diagnostic';
  if (intent === 'pricing') return 'pricing';
  return 'rag';
}

export default function ChatPage() {
  const { auth } = useAuth();
  const navigate = useNavigate();

  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!auth) {
      navigate('/login');
    }
  }, [auth, navigate]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [input]);

  const handleNewSession = useCallback(() => {
    setActiveId(null);
    setMessages([]);
  }, []);

  const handleSelectConversation = useCallback((id: string) => {
    setActiveId(id);
    setMessages([]);
    // In a real app, fetch history by conversation_id; here we just reset
  }, []);

  const handleSend = useCallback(async (override?: string) => {
    const text = (override ?? input).trim();
    if (!text || loading || !auth) return;

    const userMsg: ChatMessage = {
      id: genId(),
      role: 'user',
      content: text,
      createdAt: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.chat(text, auth.username, activeId);

      if (!activeId && res.conversation_id) {
        setActiveId(res.conversation_id);
        setConversations((prev) => [
          { id: res.conversation_id, title: text.slice(0, 40), createdAt: Date.now() },
          ...prev,
        ]);
      }

      const telemetry: ChatTelemetry | undefined = res.metadata?.route
        ? {
            intent: parseIntent(res.intent),
            confidence: res.metadata?.confidence ?? 0.9,
            route: res.metadata?.route ?? '',
            iterations: res.metadata?.iteration_count ?? 1,
          }
        : undefined;

      const assistantMsg: ChatMessage = {
        id: genId(),
        role: 'assistant',
        content: res.response,
        telemetry,
        createdAt: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Chat request failed');
      const errMsg: ChatMessage = {
        id: genId(),
        role: 'assistant',
        content: 'I encountered an error processing your request. Please try again.',
        createdAt: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, auth, activeId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!auth) return null;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] bg-[#0B0F19]">
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelectConversation}
        onNew={handleNewSession}
        onSuggestion={(t) => handleSend(t)}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
      />

      {/* Chat window */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-[60vh] text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#1F2937] border border-cyan-500/30 border-glow-cyan mb-4">
                  <Send className="h-7 w-7 text-cyan-400" />
                </div>
                <h2 className="text-xl font-bold mb-1">Flight Telemetry Assistant</h2>
                <p className="text-sm text-muted-foreground max-w-md">
                  Ask about DJI drone diagnostics, specifications, pricing, or troubleshooting. I'll analyze the knowledge base and provide detailed guidance.
                </p>
              </div>
            )}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {loading && <ThinkingIndicator />}
          </div>
        </div>

        {/* Input bar */}
        <div className="border-t border-cyan-500/10 glass-strong">
          <div className="max-w-3xl mx-auto px-4 py-3">
            <div className="relative flex items-end gap-2 rounded-xl border border-cyan-500/20 bg-[#0B0F19]/60 p-2 focus-within:border-cyan-500/40 transition-colors">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about drone diagnostics, specs, or pricing..."
                className="min-h-[40px] max-h-40 flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-sm focus-visible:ring-0 focus-visible:ring-offset-0"
                rows={1}
              />
              <button
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-white disabled:opacity-30 disabled:cursor-not-allowed hover:from-cyan-400 hover:to-blue-500 transition-all shadow-[0_0_12px_rgba(6,182,212,0.3)]"
              >
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </button>
            </div>
            <div className="mt-1.5 text-center text-[10px] font-mono text-muted-foreground/40">
              Enter to send · Shift+Enter for new line
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
