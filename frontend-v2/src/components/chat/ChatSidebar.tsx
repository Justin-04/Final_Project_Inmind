import { useState, useRef } from 'react';
import { Plus, MessageSquare, PanelLeftClose, PanelLeft, MoreHorizontal, Pencil, Trash2, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { api } from '@/services/api';
import { toast } from 'sonner';
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Menu } from 'lucide-react';

export interface ConversationMeta {
  id: string;
  title: string;
  createdAt: number;
}

const suggestions = [
  'What is the max speed of the DJI Air 3?',
  'Error code E001',
  'Show me the dji air 3 diagram',
  'How much does the dji neo weigh?',
  'How much is the DJI Mini 4 Pro?',
  'Weight of Air 3? And its price?',
  'Which is heavier, dji air 3 or mini 4 pro?',
  'Show me a beginner\'s tutorial for flying the DJI Air 3.',
  'What sensors does Air 3 have for obstacle avoidance?',
  'Can I fly in the rain?',
];


interface SidebarProps {
  conversations: ConversationMeta[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (text: string) => void;
  onDelete: (id: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function ChatSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  onDelete,
  collapsed,
  onToggleCollapse,
}: SidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const content = (
    <SidebarContent
      conversations={conversations}
      activeId={activeId}
      onSelect={(id) => { onSelect(id); setMobileOpen(false); }}
      onNew={() => { onNew(); setMobileOpen(false); }}
      onSuggestion={(t) => { onSuggestion(t); setMobileOpen(false); }}
      onDelete={onDelete}
    />
  );

  return (
    <>
      {/* Desktop sidebar */}
      <div className={cn('hidden md:flex transition-all duration-300 relative', collapsed ? 'w-0' : 'w-72')}>
        {!collapsed && (
          <div className="w-72 flex-shrink-0 border-r border-cyan-500/10 bg-[#0B0F19]/40 flex flex-col">
            {content}
            <button
              onClick={onToggleCollapse}
              className="absolute -right-3 top-6 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-[#1F2937] border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/10 transition-colors"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        {collapsed && (
          <button
            onClick={onToggleCollapse}
            className="absolute left-2 top-6 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-[#1F2937] border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/10 transition-colors"
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Mobile sidebar */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="md:hidden absolute left-2 top-2 z-30 text-cyan-400">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-72 bg-[#0B0F19] border-cyan-500/15 p-0">
          {content}
        </SheetContent>
      </Sheet>
    </>
  );
}

function SidebarContent({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  onDelete,
}: {
  conversations: ConversationMeta[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (text: string) => void;
  onDelete: (id: string) => void;
}) {
  const groups = groupByDate(conversations);

  return (
    <div className="flex h-full flex-col">
      {/* New session */}
      <div className="p-3">
        <Button
          onClick={onNew}
          className="w-full bg-gradient-to-r from-cyan-500/20 to-blue-600/20 border border-cyan-500/30 text-cyan-200 hover:from-cyan-500/30 hover:to-blue-600/30 hover:border-cyan-400/50"
          variant="outline"
        >
          <Plus className="h-4 w-4 mr-2" />
          New Telemetry Session
        </Button>
      </div>

      {/* History */}
      <div className="flex-1 overflow-y-auto scrollbar-thin px-2">
        {conversations.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-muted-foreground/50 font-mono">
            No sessions yet
          </div>
        ) : (
          Object.entries(groups).map(([label, items]) => (
            <div key={label} className="mb-3">
              <div className="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-muted-foreground/50">
                {label}
              </div>
              {items.map((conv) => (
                <ConversationItem
                  key={conv.id}
                  conv={conv}
                  isActive={activeId === conv.id}
                  onSelect={onSelect}
                  onDelete={onDelete}
                />
              ))}
            </div>
          ))
        )}
      </div>

      {/* Suggestions dropdown */}
      <div className="border-t border-cyan-500/10 p-3">
        <SuggestionsDropdown onSuggestion={onSuggestion} />
      </div>
    </div>
  );
}

function SuggestionsDropdown({ onSuggestion }: { onSuggestion: (text: string) => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-muted-foreground hover:border-cyan-500/20 hover:text-cyan-300 transition-colors"
      >
        <span className="font-mono uppercase tracking-wider text-[10px]">Demo Queries</span>
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="mt-1 space-y-1 max-h-48 overflow-y-auto scrollbar-thin">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => { onSuggestion(s); setOpen(false); }}
              className="w-full text-left rounded-md px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-cyan-500/10 hover:text-cyan-300 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function ConversationItem({ conv, isActive, onSelect, onDelete }: { conv: ConversationMeta; isActive: boolean; onSelect: (id: string) => void; onDelete: (id: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(conv.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const handleStartRename = () => {
    setMenuOpen(false);
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 50);
  };

  const handleSave = async () => {
    setEditing(false);
    const newTitle = title.trim();
    if (!newTitle || newTitle === conv.title) {
      setTitle(conv.title);
      return;
    }
    try {
      await api.renameConversation(conv.id, newTitle);
      conv.title = newTitle;
    } catch {
      setTitle(conv.title);
      toast.error('Failed to rename');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') { setTitle(conv.title); setEditing(false); }
  };

  const handleDelete = async () => {
    setMenuOpen(false);
    try {
      await api.deleteConversation(conv.id);
      onDelete(conv.id);
      toast.success('Conversation deleted');
    } catch {
      toast.error('Failed to delete');
    }
  };

  return (
    <div className="relative group">
      <button
        onClick={() => !editing && onSelect(conv.id)}
        className={cn(
          'w-full flex items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors mb-0.5',
          isActive
            ? 'bg-cyan-500/10 text-cyan-200 border border-cyan-500/20'
            : 'text-muted-foreground hover:bg-white/5 border border-transparent'
        )}
      >
        <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        {editing ? (
          <input
            ref={inputRef}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            className="flex-1 bg-transparent border-b border-cyan-500/50 outline-none text-sm text-cyan-200 px-0"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="truncate flex-1">{title}</span>
        )}
      </button>

      {/* Three-dot menu button */}
      {!editing && (
        <button
          onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
          className={cn(
            'absolute right-1.5 top-1/2 -translate-y-1/2 flex h-6 w-6 items-center justify-center rounded-md transition-all',
            menuOpen
              ? 'bg-white/10 text-cyan-300'
              : 'opacity-0 group-hover:opacity-100 text-muted-foreground/50 hover:text-cyan-300 hover:bg-white/10'
          )}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </button>
      )}

      {/* Dropdown menu */}
      {menuOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
          <div
            ref={menuRef}
            className="absolute right-0 top-full z-50 mt-1 w-36 rounded-lg border border-white/10 bg-[#1A1F2E] shadow-xl py-1"
          >
            <button
              onClick={handleStartRename}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-muted-foreground hover:text-cyan-300 hover:bg-white/5 transition-colors"
            >
              <Pencil className="h-3 w-3" />
              Rename
            </button>
            <button
              onClick={handleDelete}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 className="h-3 w-3" />
              Delete
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function groupByDate(conversations: ConversationMeta[]): Record<string, ConversationMeta[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterday = today - 86400000;

  const groups: Record<string, ConversationMeta[]> = {};
  for (const conv of conversations) {
    let label: string;
    if (conv.createdAt >= today) label = 'Today';
    else if (conv.createdAt >= yesterday) label = 'Yesterday';
    else label = 'Earlier';
    if (!groups[label]) groups[label] = [];
    groups[label].push(conv);
  }
  return groups;
}
