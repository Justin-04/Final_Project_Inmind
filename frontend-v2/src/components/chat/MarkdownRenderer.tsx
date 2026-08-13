import { useState, type ReactNode } from 'react';
import { Copy, Check } from 'lucide-react';
import { Dialog, DialogContent } from '@/components/ui/dialog';

export default function MarkdownRenderer({ content }: { content: string }) {
  const blocks = parseMarkdown(content);
  return (
    <div className="prose-chat text-sm text-foreground/90">
      {blocks.map((block, i) => renderBlock(block, i))}
    </div>
  );
}

type Block =
  | { type: 'code'; lang: string; code: string }
  | { type: 'heading'; level: number; text: string }
  | { type: 'quote'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'paragraph'; text: string };

function parseMarkdown(md: string): Block[] {
  const lines = md.split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim() || 'text';
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: 'code', lang, code: codeLines.join('\n') });
      continue;
    }

    // Heading
    const headingMatch = line.match(/^(#{1,4})\s+(.*)/);
    if (headingMatch) {
      blocks.push({ type: 'heading', level: headingMatch[1].length, text: headingMatch[2] });
      i++;
      continue;
    }

    // Blockquote
    if (line.trim().startsWith('>')) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().slice(1).trim());
        i++;
      }
      blocks.push({ type: 'quote', text: quoteLines.join(' ') });
      continue;
    }

    // Table
    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('---')) {
      const headers = line.split('|').map((h) => h.trim()).filter(Boolean);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        rows.push(lines[i].split('|').map((c) => c.trim()).filter(Boolean));
        i++;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    // List
    if (line.match(/^\s*[-*]\s+/) || line.match(/^\s*\d+\.\s+/)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const items: string[] = [];
      while (i < lines.length && (lines[i].match(/^\s*[-*]\s+/) || lines[i].match(/^\s*\d+\.\s+/))) {
        items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, ''));
        i++;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }

    // Empty line
    if (!line.trim()) {
      i++;
      continue;
    }

    // Paragraph (collect consecutive non-empty lines)
    const paraLines: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: 'paragraph', text: paraLines.join(' ') });
  }

  return blocks;
}

function isBlockStart(line: string): boolean {
  return (
    line.trim().startsWith('```') ||
    /^#{1,4}\s+/.test(line) ||
    line.trim().startsWith('>') ||
    (line.includes('|') && /^\s*\|/.test(line)) ||
    line.match(/^\s*[-*]\s+/) !== null ||
    line.match(/^\s*\d+\.\s+/) !== null
  );
}

function renderBlock(block: Block, key: number): ReactNode {
  switch (block.type) {
    case 'code':
      return <CodeBlock key={key} code={block.code} lang={block.lang} />;
    case 'heading': {
      const Tag = `h${Math.min(block.level, 3)}` as 'h1' | 'h2' | 'h3';
      return <Tag key={key}>{renderInline(block.text)}</Tag>;
    }
    case 'quote':
      return <blockquote key={key}>{renderInline(block.text)}</blockquote>;
    case 'list':
      return block.ordered ? (
        <ol key={key}>{block.items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ol>
      ) : (
        <ul key={key}>{block.items.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ul>
      );
    case 'table':
      return (
        <table key={key}>
          <thead>
            <tr>{block.headers.map((h, i) => <th key={i}>{renderInline(h)}</th>)}</tr>
          </thead>
          <tbody>
            {block.rows.map((row, i) => (
              <tr key={i}>{row.map((cell, j) => <td key={j}>{renderInline(cell)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      );
    case 'paragraph':
      return <p key={key}>{renderInline(block.text)}</p>;
  }
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group">
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#0B0F19]/80 border border-cyan-500/15 border-b-0 rounded-t-lg">
        <span className="text-[10px] font-mono text-cyan-400/60 uppercase">{lang}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-cyan-300 transition-colors"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="rounded-t-none">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function renderInline(text: string): ReactNode {
  // Handle images ![alt](url)
  const imgMatch = text.match(/!\[([^\]]*)\]\(([^)]+)\)/);
  if (imgMatch) {
    return <InlineImage alt={imgMatch[1]} url={imgMatch[2]} />;
  }

  // Handle inline formatting: **bold**, *italic*, `code`, [link](url)
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="inline">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('*') && part.endsWith('*') && !part.startsWith('**')) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    const linkMatch = part.match(/\[([^\]]+)\]\(([^)]+)\)/);
    if (linkMatch) {
      return <a key={i} href={linkMatch[2]} target="_blank" rel="noopener noreferrer">{linkMatch[1]}</a>;
    }
    return <span key={i}>{part}</span>;
  });
}

function InlineImage({ alt, url }: { alt: string; url: string }) {
  const [zoom, setZoom] = useState(false);
  return (
    <>
      <img src={url} alt={alt} onClick={() => setZoom(true)} />
      <Dialog open={zoom} onOpenChange={setZoom}>
        <DialogContent className="max-w-3xl bg-[#0B0F19]/95 border-cyan-500/20 p-2">
          <img src={url} alt={alt} className="w-full rounded-lg" />
        </DialogContent>
      </Dialog>
    </>
  );
}
