import { motion } from 'framer-motion';
import { Radar } from 'lucide-react';

export default function ThinkingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-lg bg-[#1F2937] border border-cyan-500/30 border-glow-cyan">
        <Radar className="h-4 w-4 text-cyan-400 animate-radar" />
      </div>
      <div className="glass rounded-xl border border-cyan-500/15 px-4 py-3 flex items-center gap-3">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-cyan-400"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
            />
          ))}
        </div>
        <span className="text-xs font-mono text-cyan-300/80">Analyzing Flight Logs & Telemetry...</span>
      </div>
    </motion.div>
  );
}
