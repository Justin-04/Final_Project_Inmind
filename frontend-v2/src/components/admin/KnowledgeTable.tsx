import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Search, Trash2, FileText, Database, Loader2 } from 'lucide-react';
import { api, type KnowledgeDocument } from '@/services/api';
import { useAuth } from '@/hooks/use-auth';
import { toast } from 'sonner';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export default function KnowledgeTable({ refreshKey }: { refreshKey: number }) {
  const { auth } = useAuth();
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchDocs = useCallback(async () => {
    if (auth?.role !== 'admin') return;
    setLoading(true);
    try {
      const res = await api.getDocuments();
      setDocuments(res.documents ?? []);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to fetch documents');
    } finally {
      setLoading(false);
    }
  }, [auth]);

  useEffect(() => {
    fetchDocs();
  }, [fetchDocs, refreshKey]);

  const filtered = documents.filter((d) =>
    d.drone_model.toLowerCase().includes(search.toLowerCase()) ||
    d.source.toLowerCase().includes(search.toLowerCase())
  );

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteDocument(deleteTarget);
      toast.success(`Purged "${deleteTarget}" from vector store`);
      setDeleteTarget(null);
      fetchDocs();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Deletion failed');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-2xl border border-cyan-500/15 p-6"
    >
      <div className="flex items-center gap-2 mb-4">
        <Database className="h-5 w-5 text-cyan-400" />
        <h3 className="font-semibold">Knowledge Base Inventory</h3>
        <Badge variant="outline" className="ml-auto border-cyan-500/30 text-cyan-300 font-mono">
          {documents.length} sources
        </Badge>
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by drone model or source name..."
          className="pl-10 bg-[#0B0F19]/60 border-cyan-500/20 focus-visible:ring-cyan-500/40"
        />
      </div>

      {/* Table */}
      <div className="rounded-lg border border-cyan-500/10 overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-cyan-500/15 hover:bg-transparent">
              <TableHead className="text-cyan-300/70 font-mono text-xs">SOURCE</TableHead>
              <TableHead className="text-cyan-300/70 font-mono text-xs">DRONE MODEL</TableHead>
              <TableHead className="text-cyan-300/70 font-mono text-xs text-right">VECTORS</TableHead>
              <TableHead className="text-cyan-300/70 font-mono text-xs text-right">ACTIONS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <TableRow key={i} className="border-white/5">
                  <TableCell><Skeleton className="h-5 w-32" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-28" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-12 ml-auto" /></TableCell>
                  <TableCell><Skeleton className="h-5 w-8 ml-auto" /></TableCell>
                </TableRow>
              ))
            ) : filtered.length === 0 ? (
              <TableRow className="border-white/5">
                <TableCell colSpan={4} className="text-center text-sm text-muted-foreground py-8">
                  {documents.length === 0 ? 'No documents in knowledge base' : 'No matches found'}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((doc) => (
                <TableRow key={doc.source} className="border-white/5 hover:bg-cyan-500/5">
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-cyan-400/60 flex-shrink-0" />
                      <span className="text-sm truncate max-w-[200px]">{doc.source}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="border-cyan-500/25 text-cyan-200/80 font-mono text-xs">
                      {doc.drone_model}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <span className="font-mono text-sm text-cyan-300">{doc.chunk_count}</span>
                  </TableCell>
                  <TableCell className="text-right">
                    <button
                      onClick={() => setDeleteTarget(doc.source)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Delete dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent className="glass-strong border-rose-500/20">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-rose-400" />
              Purge Document
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to purge <span className="font-mono text-rose-300">{deleteTarget}</span> from the Vector Knowledge Base? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="border-cyan-500/20">Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-500 hover:bg-rose-600 text-white"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Purge'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.div>
  );
}
