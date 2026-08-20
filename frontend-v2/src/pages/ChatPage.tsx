import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Loader2, Mic, MicOff, ChevronDown } from 'lucide-react';
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

function speakText(text: string) {
  // Strip markdown formatting for cleaner speech
  const clean = text
    .replace(/[#*_~`>\[\]()!]/g, '')
    .replace(/\n+/g, '. ')
    .replace(/\s+/g, ' ')
    .trim();
  
  if (!clean || !('speechSynthesis' in window)) return;
  
  // Cancel any ongoing speech
  speechSynthesis.cancel();
  
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.lang = 'en-US';
  speechSynthesis.speak(utterance);
}

export default function ChatPage() {
  const { auth } = useAuth();
  const navigate = useNavigate();

  const [conversations, setConversations] = useState<ConversationMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wasVoiceInputRef = useRef(false);
  const MAX_RECORDING_MS = 30000; // 30 seconds max
  const [collapsed, setCollapsed] = useState(false);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [useBert, setUseBert] = useState(true); // Toggle for BERT classifier

  useEffect(() => {
    if (!auth) {
      navigate('/login');
    }
  }, [auth, navigate]);

  // Load conversation history from MongoDB on mount
  useEffect(() => {
    if (!auth) return;
    api.getConversations(auth.username).then((res) => {
      const convs: ConversationMeta[] = (res.conversations || []).map((c: any) => ({
        id: c.conversation_id,
        title: c.title || c.conversation_id.slice(0, 8) + '...',
        createdAt: new Date(c.created_at).getTime(),
      }));
      setConversations(convs);
    }).catch(() => {});
  }, [auth]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Detect if user scrolled up
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handleScroll = () => {
      const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      setShowScrollBtn(!isNearBottom);
    };
    el.addEventListener('scroll', handleScroll);
    return () => el.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToBottom = () => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  };

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

  const handleSelectConversation = useCallback(async (id: string) => {
    setActiveId(id);
    setMessages([]);
    // Fetch conversation messages from MongoDB
    try {
      const res = await api.getConversation(id);
      if (res.messages) {
        const msgs: ChatMessage[] = res.messages.map((m: any, i: number) => ({
          id: `${id}-${i}`,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          createdAt: new Date(m.timestamp).getTime(),
        }));
        setMessages(msgs);
      }
    } catch {
      // If fetch fails, just show empty
    }
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
      const res = await api.chat(text, auth.username, activeId, useBert);

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
            cacheHit: res.metadata?.cache_hit ?? false,
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
      const isRateLimit = (err as any)?.status === 429;
      if (isRateLimit) {
        toast.warning(err instanceof Error ? err.message : 'Rate limit exceeded. Please wait before sending another message.');
      } else {
        toast.error(err instanceof Error ? err.message : 'Chat request failed');
      }
      const errMsg: ChatMessage = {
        id: genId(),
        role: 'assistant',
        content: isRateLimit
          ? 'You are sending messages too quickly. Please wait a moment before trying again.'
          : 'I encountered an error processing your request. Please try again.',
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

  const handleVoiceToggle = useCallback(async () => {
    if (recording) {
      // Stop recording
      if (recordingTimerRef.current) {
        clearTimeout(recordingTimerRef.current);
        recordingTimerRef.current = null;
      }
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    // Start recording
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });

        if (audioBlob.size < 1000) {
          toast.error('Recording too short');
          return;
        }

        if (!auth) return;

        // Transcribe only — put text in input field for user to review
        toast.info('Transcribing...');
        try {
          const formData = new FormData();
          formData.append('audio', audioBlob, 'recording.webm');
          formData.append('user_id', auth.username);

          const headers: Record<string, string> = {};
          const authState = await import('@/services/api').then(m => m.getAuth());
          if (authState?.access_token) {
            headers['Authorization'] = `Bearer ${authState.access_token}`;
          }

          const res = await fetch('/api/v1/voice/transcribe', {
            method: 'POST',
            headers,
            body: formData,
          });

          if (res.ok) {
            const data = await res.json();
            setInput(data.transcription);
            wasVoiceInputRef.current = true;
            toast.success('Transcribed! Press Enter to send.');
          } else {
            toast.error('Transcription failed');
          }
        } catch (err) {
          toast.error('Transcription failed');
        }
      };

      mediaRecorder.start();
      setRecording(true);
      toast.info('Recording... click again to stop (max 30s)');

      // Auto-stop after 30 seconds
      recordingTimerRef.current = setTimeout(() => {
        if (mediaRecorderRef.current?.state === 'recording') {
          mediaRecorderRef.current.stop();
          setRecording(false);
          toast.info('Max recording time reached');
        }
      }, MAX_RECORDING_MS);
    } catch (err) {
      toast.error('Microphone access denied');
    }
  }, [recording, auth, activeId]);

  if (!auth) return null;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] bg-[#0B0F19]">
      <ChatSidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelectConversation}
        onNew={handleNewSession}
        onSuggestion={(t) => handleSend(t)}
        onDelete={(id) => {
          setConversations((prev) => prev.filter((c) => c.id !== id));
          if (activeId === id) {
            setActiveId(null);
            setMessages([]);
          }
        }}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
      />

      {/* Chat window */}
      <div className="flex-1 flex flex-col min-w-0 relative">
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
            {messages.map((msg, idx) => (
              <MessageBubble key={msg.id} message={msg} conversationId={activeId} messageIndex={idx} />
            ))}
            {loading && <ThinkingIndicator />}
          </div>
        </div>

        {/* Scroll to bottom button */}
        {showScrollBtn && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-24 right-6 flex h-9 w-9 items-center justify-center rounded-full bg-[#1F2937] border border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/10 transition-all shadow-lg z-10"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        )}

        {/* Input bar */}
        <div className="border-t border-cyan-500/10 glass-strong">
          <div className="max-w-3xl mx-auto px-4 py-3">
            {/* BERT Toggle */}
            <div className="flex items-center justify-between mb-2 px-1">
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">BERT Classifier:</span>
                <button
                  onClick={() => setUseBert(!useBert)}
                  className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                    useBert ? 'bg-cyan-500' : 'bg-gray-600'
                  }`}
                  title={useBert ? 'BERT enabled (fast routing)' : 'BERT disabled (always use LLM supervisor)'}
                >
                  <span
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      useBert ? 'translate-x-5' : 'translate-x-1'
                    }`}
                  />
                </button>
                <span className="text-[10px] text-muted-foreground/70">
                  {useBert ? 'Enabled (fast)' : 'Disabled (LLM only)'}
                </span>
              </div>
            </div>
            
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
                onClick={handleVoiceToggle}
                disabled={loading}
                className={`flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-lg transition-all ${
                  recording
                    ? 'bg-red-500 animate-pulse shadow-[0_0_12px_rgba(239,68,68,0.5)]'
                    : 'bg-[#1F2937] border border-cyan-500/20 hover:border-cyan-500/50 text-cyan-400'
                } disabled:opacity-30 disabled:cursor-not-allowed`}
              >
                {recording ? <MicOff className="h-4 w-4 text-white" /> : <Mic className="h-4 w-4" />}
              </button>
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
