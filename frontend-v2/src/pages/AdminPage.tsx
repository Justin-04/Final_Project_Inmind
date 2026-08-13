import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '@/hooks/use-auth';
import IngestionPortal from '@/components/admin/IngestionPortal';
import KnowledgeTable from '@/components/admin/KnowledgeTable';

export default function AdminPage() {
  const { auth } = useAuth();
  const navigate = useNavigate();
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!auth) {
      navigate('/login');
    } else if (auth.role !== 'admin') {
      navigate('/');
    }
  }, [auth, navigate]);

  if (!auth || auth.role !== 'admin') return null;

  return (
    <div className="min-h-[calc(100vh-3.5rem)] bg-[#0B0F19] scrollbar-thin overflow-y-auto">
      <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/30">
            <ShieldAlert className="h-5 w-5 text-amber-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Admin Operations Hub</h1>
            <p className="text-xs text-muted-foreground font-mono">Vector knowledge base management & document ingestion</p>
          </div>
        </div>

        <IngestionPortal onIngested={() => setRefreshKey((k) => k + 1)} />
        <KnowledgeTable refreshKey={refreshKey} />
      </div>
    </div>
  );
}
