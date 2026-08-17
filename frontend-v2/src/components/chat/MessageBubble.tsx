import { useState } from 'react';
import { motion } from 'framer-motion';
import { Hexagon, User as UserIcon, Volume2, ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, type ChatMessage } from '@/services/api';
import { toast } from 'sonner';
import MarkdownRenderer from './MarkdownRenderer';
import TelemetryBar from './TelemetryBar';

function speakText(text: string) {
  const clean = text
    .replace(/[#*_~`>\[\]()!]/g, '')
    .replace(/\n+/g, '. ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!clean || !('speechSynthesis' in window)) return;
  speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(clean);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.lang = 'en-US';
  speechSynthesis.speak(utterance);
}

interface MessageBubbleProps {
  message: ChatMessage;
  conversationId?: string | null;
  messageIndex?: number;
}

export default function MessageBubble({ message, conversationId, messageIndex }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [feedback, setFeedback] = useState<1 | -1 | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleFeedback = async (rating: 1 | -1) => {
    if (!conversationId || messageIndex === undefined || submitting) return;

    // Toggle off if same rating clicked again
    if (feedback === rating) {
      setFeedback(null);
      return;
    }

    setSubmitting(true);
    try {
      await api.submitFeedback(conversationId, messageIndex, rating);
      setFeedback(rating);
      toast.success(rating === 1 ? 'Thanks for the feedback!' : 'Sorry about that. We\'ll improve.');
    } catch {
      toast.error('Failed to submit feedback');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn('flex gap-3', isUser ? 'flex-row-reverse' : 'flex-row')}
    >
      {/* Avatar */}
      <div className={cn(
        'flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-lg border',
        isUser
          ? 'bg-blue-600/20 border-blue-500/30'
          : 'bg-[#1F2937] border-cyan-500/30 border-glow-cyan'
      )}>
        {isUser ? (
          <UserIcon className="h-4 w-4 text-blue-300" />
        ) : (
          <Hexagon className="h-4 w-4 text-cyan-400" strokeWidth={1.5} />
        )}
      </div>

      {/* Bubble */}
      <div className={cn('max-w-[80%] sm:max-w-[75%]', isUser && 'flex flex-col items-end')}>
        <div className={cn(
          'rounded-xl px-4 py-3',
          isUser
            ? 'bg-gradient-to-br from-blue-600/30 to-blue-700/20 border border-blue-500/30 text-foreground'
            : 'glass border border-cyan-500/15'
        )}>
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>

        {/* Action bar for assistant messages */}
        {!isUser && message.content && (
          <div className="mt-1.5 flex items-center gap-3">
            {/* TTS */}
            <button
              onClick={() => speakText(message.content)}
              className="flex items-center gap-1 text-[10px] text-muted-foreground/50 hover:text-cyan-400 transition-colors"
              title="Read aloud"
            >
              <Volume2 className="h-3 w-3" />
              <span>Listen</span>
            </button>

            {/* Feedback buttons */}
            {conversationId && messageIndex !== undefined && (
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleFeedback(1)}
                  disabled={submitting}
                  className={cn(
                    'flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] transition-all',
                    feedback === 1
                      ? 'bg-green-500/20 text-green-400 border border-green-500/40'
                      : 'text-muted-foreground/40 hover:text-green-400 hover:bg-green-500/10'
                  )}
                  title="Good response"
                >
                  <ThumbsUp className="h-3 w-3" />
                </button>
                <button
                  onClick={() => handleFeedback(-1)}
                  disabled={submitting}
                  className={cn(
                    'flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] transition-all',
                    feedback === -1
                      ? 'bg-red-500/20 text-red-400 border border-red-500/40'
                      : 'text-muted-foreground/40 hover:text-red-400 hover:bg-red-500/10'
                  )}
                  title="Poor response"
                >
                  <ThumbsDown className="h-3 w-3" />
                </button>
              </div>
            )}
          </div>
        )}

        {message.telemetry && <TelemetryBar telemetry={message.telemetry} />}
      </div>
    </motion.div>
  );
}
