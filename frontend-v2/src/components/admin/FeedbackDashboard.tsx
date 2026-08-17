import { useState, useEffect } from 'react';
import { ThumbsUp, ThumbsDown, MessageSquare, TrendingUp, Eye, X } from 'lucide-react';
import { api, type FeedbackItem } from '@/services/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface ConversationModal {
  conversationId: string;
  messages: Array<{ role: string; content: string; timestamp: string }>;
}

export default function FeedbackDashboard() {
  const [feedback, setFeedback] = useState<FeedbackItem[]>([]);
  const [stats, setStats] = useState({ total: 0, positive: 0, negative: 0, satisfaction_rate: 0 });
  const [filter, setFilter] = useState<'all' | 'positive' | 'negative'>('all');
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<ConversationModal | null>(null);

  useEffect(() => {
    loadFeedback();
  }, [filter]);

  const loadFeedback = async () => {
    setLoading(true);
    try {
      const rating = filter === 'positive' ? 1 : filter === 'negative' ? -1 : undefined;
      const res = await api.getAdminFeedback(rating, 50);
      setFeedback(res.feedback);
      setStats(res.stats);
    } catch {
      toast.error('Failed to load feedback');
    } finally {
      setLoading(false);
    }
  };

  const openConversation = async (conversationId: string) => {
    try {
      const res = await api.getConversation(conversationId);
      setModal({ conversationId, messages: res.messages });
    } catch {
      toast.error('Failed to load conversation');
    }
  };

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <StatCard
          icon={<MessageSquare className="h-4 w-4 text-cyan-400" />}
          label="Total Reviews"
          value={stats.total}
          color="border-cyan-500/30 bg-cyan-500/5"
        />
        <StatCard
          icon={<ThumbsUp className="h-4 w-4 text-green-400" />}
          label="Positive"
          value={stats.positive}
          color="border-green-500/30 bg-green-500/5"
        />
        <StatCard
          icon={<ThumbsDown className="h-4 w-4 text-red-400" />}
          label="Negative"
          value={stats.negative}
          color="border-red-500/30 bg-red-500/5"
        />
        <StatCard
          icon={<TrendingUp className="h-4 w-4 text-purple-400" />}
          label="Satisfaction"
          value={`${stats.satisfaction_rate}%`}
          color="border-purple-500/30 bg-purple-500/5"
        />
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-2">
        {(['all', 'negative', 'positive'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-lg border transition-all',
              filter === f
                ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300'
                : 'border-white/10 bg-white/5 text-muted-foreground hover:border-white/20'
            )}
          >
            {f === 'all' ? 'All' : f === 'negative' ? 'Negative Only' : 'Positive Only'}
          </button>
        ))}
      </div>

      {/* Feedback list */}
      <div className="space-y-2">
        {loading ? (
          <p className="text-sm text-muted-foreground py-4 text-center">Loading...</p>
        ) : feedback.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">No feedback yet</p>
        ) : (
          feedback.map((item, idx) => (
            <FeedbackRow key={idx} item={item} onViewConversation={openConversation} />
          ))
        )}
      </div>

      {/* Conversation modal */}
      {modal && (
        <ConversationViewer modal={modal} onClose={() => setModal(null)} />
      )}
    </div>
  );
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: number | string; color: string }) {
  return (
    <div className={cn('rounded-lg border px-4 py-3', color)}>
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-[10px] font-mono text-muted-foreground uppercase">{label}</span>
      </div>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}

function FeedbackRow({ item, onViewConversation }: { item: FeedbackItem; onViewConversation: (id: string) => void }) {
  const isNegative = item.rating === -1;

  return (
    <div className={cn(
      'rounded-lg border p-3 space-y-2',
      isNegative ? 'border-red-500/20 bg-red-500/5' : 'border-green-500/20 bg-green-500/5'
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isNegative ? (
            <ThumbsDown className="h-3.5 w-3.5 text-red-400" />
          ) : (
            <ThumbsUp className="h-3.5 w-3.5 text-green-400" />
          )}
          <span className="text-xs font-mono text-muted-foreground">
            {item.user_id} · {new Date(item.created_at).toLocaleDateString()}
          </span>
          {item.conversation_title && (
            <span className="text-[10px] text-muted-foreground/60 truncate max-w-[150px]">
              {item.conversation_title}
            </span>
          )}
        </div>
        <button
          onClick={() => onViewConversation(item.conversation_id)}
          className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
        >
          <Eye className="h-3 w-3" />
          <span>View Chat</span>
        </button>
      </div>

      {/* User query */}
      {item.user_query && (
        <div className="text-xs">
          <span className="text-muted-foreground/60 font-mono">Q: </span>
          <span className="text-muted-foreground">{item.user_query}</span>
        </div>
      )}

      {/* Flagged message */}
      {item.flagged_message && (
        <div className="text-xs">
          <span className="text-muted-foreground/60 font-mono">A: </span>
          <span className={cn('text-sm', isNegative ? 'text-red-200/80' : 'text-green-200/80')}>
            {item.flagged_message}
          </span>
        </div>
      )}

      {/* Comment */}
      {item.comment && (
        <div className="text-xs italic text-muted-foreground/70 border-l-2 border-white/10 pl-2">
          "{item.comment}"
        </div>
      )}
    </div>
  );
}

function ConversationViewer({ modal, onClose }: { modal: ConversationModal; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[80vh] rounded-xl border border-cyan-500/20 bg-[#0B0F19] shadow-2xl flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
          <h3 className="text-sm font-semibold">Conversation: {modal.conversationId.slice(0, 12)}...</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin">
          {modal.messages.map((msg, i) => (
            <div key={i} className={cn(
              'rounded-lg px-3 py-2 text-sm max-w-[85%]',
              msg.role === 'user'
                ? 'ml-auto bg-blue-600/20 border border-blue-500/30'
                : 'bg-[#1F2937] border border-white/10'
            )}>
              <div className="text-[10px] font-mono text-muted-foreground/50 mb-1">
                {msg.role === 'user' ? 'User' : 'Assistant'} · {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
