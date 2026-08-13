import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Hexagon, LogOut, MessageSquare, Shield, User as UserIcon } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useAuth } from '@/hooks/use-auth';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

export default function Header() {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [logoutOpen, setLogoutOpen] = useState(false);

  if (!auth) return null;

  const isAdmin = auth.role === 'admin';
  const onAdmin = location.pathname === '/admin';

  return (
    <header className="sticky top-0 z-40 glass-strong border-b border-cyan-500/15">
      <div className="flex items-center justify-between px-4 sm:px-6 h-14">
        {/* Left - brand */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2.5 group"
        >
          <Hexagon className="h-6 w-6 text-cyan-400 group-hover:drop-shadow-[0_0_8px_rgba(34,211,238,0.6)] transition-all" strokeWidth={1.5} />
          <span className="text-sm sm:text-base font-bold tracking-tight text-glow-cyan hidden sm:inline">
            DJI FlightControl AI
          </span>
          <span className="text-xs font-mono text-cyan-400/60 border border-cyan-500/30 rounded px-1.5 py-0.5 hidden md:inline">
            v2.4 Multimodal
          </span>
        </button>

        {/* Right - controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {isAdmin && (
            <div className="flex items-center rounded-lg bg-[#0B0F19]/60 border border-cyan-500/15 p-0.5">
              <button
                onClick={() => navigate('/')}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all',
                  !onAdmin ? 'bg-cyan-500/15 text-cyan-300' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Assistant</span>
              </button>
              <button
                onClick={() => navigate('/admin')}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2.5 sm:px-3 py-1.5 text-xs font-medium transition-all',
                  onAdmin ? 'bg-amber-500/15 text-amber-300' : 'text-muted-foreground hover:text-foreground'
                )}
              >
                <Shield className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Admin</span>
              </button>
            </div>
          )}

          {/* User chip */}
          <div className="flex items-center gap-2 rounded-lg bg-[#0B0F19]/60 border border-cyan-500/15 px-2.5 py-1.5">
            <div className={cn(
              'flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold',
              isAdmin ? 'bg-amber-500/20 text-amber-300' : 'bg-cyan-500/20 text-cyan-300'
            )}>
              {auth.username.charAt(0).toUpperCase()}
            </div>
            <span className="text-xs font-medium text-foreground hidden sm:inline">{auth.username}</span>
            <span className={cn(
              'text-[10px] font-mono font-bold px-1.5 py-0.5 rounded',
              isAdmin
                ? 'bg-amber-500/15 text-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.3)]'
                : 'bg-cyan-500/15 text-cyan-300 shadow-[0_0_8px_rgba(34,211,238,0.3)]'
            )}>
              {isAdmin ? 'ADMIN' : 'USER'}
            </span>
          </div>

          {/* Logout */}
          <AlertDialog open={logoutOpen} onOpenChange={setLogoutOpen}>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon" className="text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10">
                <LogOut className="h-4 w-4" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent className="glass-strong border-cyan-500/20">
              <AlertDialogHeader>
                <AlertDialogTitle>Sign out?</AlertDialogTitle>
                <AlertDialogDescription>
                  You will be returned to the login screen. Your session will be cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="border-cyan-500/20">Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-rose-500 hover:bg-rose-600 text-white"
                  onClick={() => { logout(); navigate('/login'); }}
                >
                  Sign Out
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </header>
  );
}
