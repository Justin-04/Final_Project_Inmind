import { motion } from 'framer-motion';
import { Hexagon, User as UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMessage } from '@/services/api';
import MarkdownRenderer from './MarkdownRenderer';
import TelemetryBar from './TelemetryBar';

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

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
        {message.telemetry && <TelemetryBar telemetry={message.telemetry} />}
      </div>
    </motion.div>
  );
}
