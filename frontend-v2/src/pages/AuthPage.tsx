import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Eye, EyeOff, Loader2, Lock, User, Hexagon, ShieldCheck, Radar, Database } from 'lucide-react';
import { useAuth } from '@/hooks/use-auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';
import type { Role } from '@/services/api';
import { toast } from 'sonner';

export default function AuthPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<Role>('user');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      toast.error('Please fill in all fields');
      return;
    }
    if (password.length < 4) {
      toast.error('Password must be at least 4 characters');
      return;
    }
    setLoading(true);
    try {
      if (mode === 'login') {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), password, role);
      }
      navigate('/');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-[#0B0F19] text-foreground">
      {/* Left side - telemetry graphic */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden border-r border-cyan-500/10">
        <div className="absolute inset-0 grid-bg" />
        <div className="absolute inset-0 radar-bg" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96">
          <div className="absolute inset-0 rounded-full border border-cyan-500/20" />
          <div className="absolute inset-8 rounded-full border border-cyan-500/15" />
          <div className="absolute inset-16 rounded-full border border-cyan-500/10" />
          <div className="absolute inset-24 rounded-full border border-cyan-500/5" />
          <motion.div
            className="absolute inset-0 rounded-full"
            style={{
              background: 'conic-gradient(from 0deg, transparent 0deg, rgba(34,211,238,0.25) 40deg, transparent 80deg)',
            }}
            animate={{ rotate: 360 }}
            transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
          />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_20px_rgba(34,211,238,0.8)]" />
        </div>
        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <div className="flex items-center gap-3">
            <Hexagon className="h-8 w-8 text-cyan-400" strokeWidth={1.5} />
            <span className="text-xl font-bold tracking-tight text-glow-cyan">DJI FlightControl AI</span>
          </div>
          <div className="space-y-4">
            <h1 className="text-4xl font-bold leading-tight">
              Intelligent Telemetry<br />
              <span className="text-cyan-400 text-glow-cyan">for Every Mission</span>
            </h1>
            <p className="text-muted-foreground max-w-md">
              AI-powered diagnostic assistant for DJI drone fleets. Real-time analysis, retrieval-augmented guidance, and operational intelligence.
            </p>
            <div className="space-y-2 pt-2">
              {[
                { icon: Radar, label: 'Multi-Agent Fleet Support' },
                { icon: ShieldCheck, label: 'Real-time Diagnostic Telemetry' },
                { icon: Database, label: 'S3 Retrieval Enabled' },
              ].map(({ icon: Icon, label }) => (
                <div key={label} className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Icon className="h-4 w-4 text-cyan-400/70" />
                  <span>{label}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="text-xs font-mono text-muted-foreground/50">v2.4 Multimodal · Build 2026.08</div>
        </div>
      </div>

      {/* Right side - auth card */}
      <div className="flex-1 flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-md"
        >
          <div className="lg:hidden flex items-center gap-3 mb-8 justify-center">
            <Hexagon className="h-7 w-7 text-cyan-400" strokeWidth={1.5} />
            <span className="text-lg font-bold text-glow-cyan">DJI FlightControl AI</span>
          </div>
          <div className="glass-strong rounded-2xl border border-cyan-500/20 border-glow-cyan p-8">
            <Tabs value={mode} onValueChange={(v) => setMode(v as 'login' | 'register')}>
              <TabsList className="grid w-full grid-cols-2 bg-[#0B0F19]/60">
                <TabsTrigger value="login" className="data-[state=active]:bg-cyan-500/15 data-[state=active]:text-cyan-300">Sign In</TabsTrigger>
                <TabsTrigger value="register" className="data-[state=active]:bg-cyan-500/15 data-[state=active]:text-cyan-300">Register</TabsTrigger>
              </TabsList>
              <TabsContent value="login">
                <form onSubmit={handleSubmit} className="space-y-4 mt-6">
                  <Field username={username} password={password} showPassword={showPassword}
                    setUsername={setUsername} setPassword={setPassword} setShowPassword={setShowPassword} />
                  <SubmitButton loading={loading} label="Sign In" />
                </form>
              </TabsContent>
              <TabsContent value="register">
                <form onSubmit={handleSubmit} className="space-y-4 mt-6">
                  <Field username={username} password={password} showPassword={showPassword}
                    setUsername={setUsername} setPassword={setPassword} setShowPassword={setShowPassword} />
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-muted-foreground">ROLE</label>
                    <div className="grid grid-cols-2 gap-2">
                      {(['user', 'admin'] as Role[]).map((r) => (
                        <button
                          key={r}
                          type="button"
                          onClick={() => setRole(r)}
                          className={cn(
                            'rounded-lg border px-4 py-2 text-sm font-medium transition-all',
                            role === r
                              ? r === 'admin'
                                ? 'border-amber-500/50 bg-amber-500/10 text-amber-300'
                                : 'border-cyan-500/50 bg-cyan-500/10 text-cyan-300'
                              : 'border-white/10 bg-transparent text-muted-foreground hover:border-white/20'
                          )}
                        >
                          {r === 'admin' ? 'Admin' : 'User'}
                        </button>
                      ))}
                    </div>
                  </div>
                  <SubmitButton loading={loading} label="Create Account" />
                </form>
              </TabsContent>
            </Tabs>
          </div>
          <p className="text-center text-xs text-muted-foreground/50 mt-6 font-mono">
            Secure access · Bearer token authentication
          </p>
        </motion.div>
      </div>
    </div>
  );
}

function Field(props: {
  username: string; password: string; showPassword: boolean;
  setUsername: (v: string) => void; setPassword: (v: string) => void; setShowPassword: (v: boolean) => void;
}) {
  return (
    <>
      <div className="space-y-2">
        <label className="text-xs font-mono text-muted-foreground">USERNAME</label>
        <div className="relative">
          <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={props.username}
            onChange={(e) => props.setUsername(e.target.value)}
            placeholder="pilot_callsign"
            className="pl-10 bg-[#0B0F19]/60 border-cyan-500/20 focus-visible:ring-cyan-500/40"
            autoComplete="username"
          />
        </div>
      </div>
      <div className="space-y-2">
        <label className="text-xs font-mono text-muted-foreground">PASSWORD</label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type={props.showPassword ? 'text' : 'password'}
            value={props.password}
            onChange={(e) => props.setPassword(e.target.value)}
            placeholder="••••••••"
            className="pl-10 pr-10 bg-[#0B0F19]/60 border-cyan-500/20 focus-visible:ring-cyan-500/40"
            autoComplete={props.showPassword ? 'off' : 'current-password'}
          />
          <button
            type="button"
            onClick={() => props.setShowPassword(!props.showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-cyan-300 transition-colors"
          >
            {props.showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </>
  );
}

function SubmitButton({ loading, label }: { loading: boolean; label: string }) {
  return (
    <Button
      type="submit"
      disabled={loading}
      className="w-full bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white border-0 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
    >
      {loading ? (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
          Authenticating...
        </>
      ) : (
        label
      )}
    </Button>
  );
}
