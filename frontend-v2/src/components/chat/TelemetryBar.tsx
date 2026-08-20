import { BookOpen, Wrench, Tag, Cpu, Route, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatTelemetry } from '@/services/api';

const intentConfig = {
  rag: { icon: BookOpen, label: 'RAG Agent', color: 'text-blue-300', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  diagnostic: { icon: Wrench, label: 'Diagnostic', color: 'text-amber-300', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  pricing: { icon: Tag, label: 'Pricing', color: 'text-emerald-300', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
};

export default function TelemetryBar({ telemetry }: { telemetry: ChatTelemetry }) {
  const cfg = intentConfig[telemetry.intent] ?? intentConfig.rag;
  const Icon = cfg.icon;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-mono">
      {/* Route */}
      <div className={cn('flex items-center gap-1 rounded-md border px-2 py-1', cfg.bg, cfg.border, cfg.color)}>
        <Icon className="h-3 w-3" />
        <span className="font-semibold">{telemetry.route}</span>
      </div>

      {/* Cache hit indicator */}
      {telemetry.cacheHit && (
        <div className="flex items-center gap-1 rounded-md border border-purple-500/30 bg-purple-500/10 px-2 py-1 text-purple-300">
          <Zap className="h-3 w-3" />
          <span className="font-semibold">Cached</span>
        </div>
      )}
    </div>
  );
}
