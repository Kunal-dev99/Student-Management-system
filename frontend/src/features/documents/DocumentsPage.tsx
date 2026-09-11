'use client'

/**
 * Student document library.
 *
 * Files are grouped by category (thesis, milestone submissions, research outputs,
 * training, ethics, meetings, admin, other). Upload with a category picker; preview
 * PDFs and images inline; download anything.
 *
 * This is a *library*, not the record — the portal still hosts the lifecycle. Documents
 * lives here so it's findable and browsable without wading through supervision + funding
 * to get to it.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  BookOpen, ClipboardCheck, Download, Eye, FileText, FlaskConical, Gavel,
  GraduationCap, MessageSquare, Package, Upload,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/components/ui/use-toast'
import { cn } from '@/lib/utils'
import {
  downloadPortalDocument,
  fetchPortalDocumentResponse,
  useMyDocuments,
  useUploadMyDocument,
  type DocumentCategory,
  type PortalDocument,
} from '@/features/portal/api'

interface CategoryDef {
  key: DocumentCategory
  label: string
  icon: typeof FileText
  description: string
}

const CATEGORIES: CategoryDef[] = [
  { key: 'thesis', label: 'Thesis',
    icon: BookOpen, description: 'Chapters, drafts, complete thesis, corrections.' },
  { key: 'milestone', label: 'Milestone submissions',
    icon: ClipboardCheck, description: 'Reports and evidence for confirmation, transfer viva, annual review.' },
  { key: 'research', label: 'Research outputs',
    icon: FlaskConical, description: 'Papers, posters, presentations, published work.' },
  { key: 'training', label: 'Training & CPD',
    icon: GraduationCap, description: 'Course certificates, training records, PGR skills log.' },
  { key: 'ethics', label: 'Ethics & governance',
    icon: Gavel, description: 'Ethics approvals, data management plans, IP declarations.' },
  { key: 'meetings', label: 'Meetings',
    icon: MessageSquare, description: 'Supervision meeting notes, panel minutes.' },
  { key: 'admin', label: 'Admin & correspondence',
    icon: FileText, description: 'Extension requests, official letters, upgrade forms.' },
  { key: 'other', label: 'Other',
    icon: Package, description: 'Anything else.' },
]

const CATEGORY_META = new Map(CATEGORIES.map((c) => [c.key, c]))

type UiFilter = DocumentCategory | 'all'

export function DocumentsPage() {
  const { data, isLoading } = useMyDocuments()
  const upload = useUploadMyDocument()
  const { toast } = useToast()

  const [filter, setFilter] = useState<UiFilter>('all')
  const [uploadCategory, setUploadCategory] = useState<DocumentCategory>('thesis')
  const [preview, setPreview] = useState<PortalDocument | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)

  const byCategory = useMemo(() => {
    const groups = new Map<DocumentCategory, PortalDocument[]>()
    for (const c of CATEGORIES) groups.set(c.key, [])
    for (const d of data ?? []) {
      const bucket = groups.get(d.category) ?? groups.get('other')!
      bucket.push(d)
    }
    return groups
  }, [data])

  const total = data?.length ?? 0
  const filtered = filter === 'all' ? data ?? [] : byCategory.get(filter) ?? []

  const handleUpload = async (file: File) => {
    try {
      await upload.mutateAsync({ file, category: uploadCategory })
      toast({ title: 'Uploaded', description: `${file.name} filed under ${CATEGORY_META.get(uploadCategory)?.label}.` })
    } catch {
      toast({ title: 'Upload failed', description: 'Please try again.', variant: 'destructive' })
    }
    if (fileInput.current) fileInput.current.value = ''
  }

  const handleDownload = async (doc: PortalDocument) => {
    try {
      await downloadPortalDocument(doc.id, doc.filename)
    } catch {
      toast({ title: 'Download failed', variant: 'destructive' })
    }
  }

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page-title flex items-center gap-2">
            <FileText className="h-6 w-6 text-primary" />
            Documents
          </h1>
          <p className="text-helper mt-1">
            Your files, organised. Thesis drafts, milestone evidence, training certificates,
            correspondence — one library, categorised and searchable.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Select value={uploadCategory} onValueChange={(v) => setUploadCategory(v as DocumentCategory)}>
            <SelectTrigger className="w-56 h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <input
            ref={fileInput}
            type="file"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleUpload(file)
            }}
          />
          <Button onClick={() => fileInput.current?.click()} disabled={upload.isPending}>
            <Upload className="h-4 w-4 mr-1.5" />
            {upload.isPending ? 'Uploading…' : 'Upload'}
          </Button>
        </div>
      </header>

      {/* Category rail — all + one chip per category with counts */}
      <div className="flex flex-wrap items-center gap-1.5">
        <CategoryChip
          active={filter === 'all'}
          onClick={() => setFilter('all')}
          label="All"
          count={total}
        />
        {CATEGORIES.map((c) => {
          const count = byCategory.get(c.key)?.length ?? 0
          if (count === 0 && filter !== c.key) return null
          const Icon = c.icon
          return (
            <CategoryChip
              key={c.key}
              active={filter === c.key}
              onClick={() => setFilter(c.key)}
              icon={<Icon className="h-3 w-3" />}
              label={c.label}
              count={count}
            />
          )
        })}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : filter === 'all' ? (
        <div className="space-y-8">
          {CATEGORIES.map((c) => {
            const docs = byCategory.get(c.key) ?? []
            if (docs.length === 0) return null
            return (
              <CategorySection
                key={c.key}
                def={c}
                docs={docs}
                onPreview={setPreview}
                onDownload={handleDownload}
              />
            )
          })}
          {total === 0 && (
            <EmptyState onUpload={() => fileInput.current?.click()} />
          )}
        </div>
      ) : (
        <CategorySection
          def={CATEGORY_META.get(filter)!}
          docs={filtered}
          onPreview={setPreview}
          onDownload={handleDownload}
          expanded
        />
      )}

      <PreviewDialog
        doc={preview}
        onOpenChange={(open) => !open && setPreview(null)}
        onDownload={handleDownload}
      />
    </div>
  )
}

function CategoryChip({
  active, onClick, label, count, icon,
}: {
  active: boolean
  onClick: () => void
  label: string
  count: number
  icon?: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
        active
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-border bg-card text-muted-foreground hover:border-primary/30 hover:text-foreground',
      )}
    >
      {icon}
      {label}
      <span className={cn(
        'num rounded-full px-1.5 min-w-[1.25rem] text-center',
        active ? 'bg-primary/15' : 'bg-muted',
      )}>
        {count}
      </span>
    </button>
  )
}

function CategorySection({
  def, docs, onPreview, onDownload, expanded,
}: {
  def: CategoryDef
  docs: PortalDocument[]
  onPreview: (doc: PortalDocument) => void
  onDownload: (doc: PortalDocument) => void
  expanded?: boolean
}) {
  const Icon = def.icon
  return (
    <section className={cn('space-y-3', expanded && 'pt-2')}>
      <div className="flex items-baseline gap-3">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <h2 className="text-base font-medium">{def.label}</h2>
        </div>
        <p className="text-helper text-xs">{def.description}</p>
      </div>
      {docs.length === 0 ? (
        <p className="text-helper text-sm">Nothing here yet.</p>
      ) : (
        <ul className="divide-y divide-border/60 rounded-md border border-border overflow-hidden">
          {docs.map((doc) => (
            <DocumentRow
              key={doc.id}
              doc={doc}
              onPreview={onPreview}
              onDownload={onDownload}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function DocumentRow({
  doc, onPreview, onDownload,
}: {
  doc: PortalDocument
  onPreview: (doc: PortalDocument) => void
  onDownload: (doc: PortalDocument) => void
}) {
  const canPreview = isPreviewable(doc.contentType)
  const scanning = doc.scanStatus !== 'clean'

  return (
    <li className="flex items-center gap-3 px-4 py-3 hover:bg-muted/40">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{doc.filename}</p>
        <p className="text-xs text-muted-foreground">
          {formatSize(doc.sizeBytes)}
          {doc.createdAt && ` · ${new Date(doc.createdAt).toLocaleDateString()}`}
          {doc.ownerType === 'milestone' && (
            <span className="ml-2 text-[hsl(var(--info))]">Milestone submission</span>
          )}
        </p>
      </div>
      {scanning ? (
        <Badge variant="outline" className="text-xs">
          {doc.scanStatus === 'infected' ? 'Quarantined' : 'Scanning'}
        </Badge>
      ) : (
        <div className="flex items-center gap-1">
          {canPreview && (
            <Button
              size="sm"
              variant="ghost"
              className="h-8"
              onClick={() => onPreview(doc)}
            >
              <Eye className="h-3.5 w-3.5 mr-1" />
              Preview
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() => onDownload(doc)}
          >
            <Download className="h-3.5 w-3.5 mr-1" />
            Download
          </Button>
        </div>
      )}
    </li>
  )
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="rounded-md border border-dashed border-border px-6 py-12 text-center">
      <FileText className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
      <p className="text-sm font-medium mb-1">Nothing here yet</p>
      <p className="text-helper text-sm mb-4">
        Start by uploading your first draft, certificate, or approval.
      </p>
      <Button onClick={onUpload}>
        <Upload className="h-4 w-4 mr-1.5" />
        Upload a file
      </Button>
    </div>
  )
}

// ---------- Preview

function PreviewDialog({
  doc, onOpenChange, onDownload,
}: {
  doc: PortalDocument | null
  onOpenChange: (open: boolean) => void
  onDownload: (doc: PortalDocument) => void
}) {
  return (
    <Dialog open={!!doc} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl h-[80vh] p-0 gap-0 flex flex-col">
        <DialogHeader className="px-5 py-3 border-b border-border flex-row items-center justify-between space-y-0">
          <DialogTitle className="text-base font-medium truncate max-w-[60%]">
            {doc?.filename}
          </DialogTitle>
          {/* Right-pad reserves space for shadcn Dialog's built-in ✕ button (top-right, 16px).
              We only render the Download action here — no second X, or you get two of them. */}
          <div className="flex items-center gap-1 pr-8">
            {doc && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => onDownload(doc)}
              >
                <Download className="h-3.5 w-3.5 mr-1" />
                Download
              </Button>
            )}
          </div>
        </DialogHeader>
        <div className="flex-1 min-h-0 bg-muted/30">
          {doc && <PreviewBody doc={doc} />}
        </div>
      </DialogContent>
    </Dialog>
  )
}

type PreviewState =
  | { kind: 'loading' }
  | { kind: 'ready-native'; url: string; contentType: string }
  | { kind: 'ready-html'; html: string }
  | { kind: 'ready-audio'; url: string; contentType: string }
  | { kind: 'ready-video'; url: string; contentType: string }
  | { kind: 'unsupported'; contentType: string }
  | { kind: 'error'; message: string }

const OFFICE_DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const OFFICE_XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const OFFICE_PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
const OFFICE_LEGACY_DOC = 'application/msword'
const OFFICE_LEGACY_XLS = 'application/vnd.ms-excel'

function PreviewBody({ doc }: { doc: PortalDocument }) {
  const [state, setState] = useState<PreviewState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    let revokeUrl: string | null = null

    const load = async () => {
      try {
        // Reuse the shared api.raw path — carries the bearer, handles 401-refresh.
        const res = await fetchPortalDocumentResponse(doc.id)
        const contentType = (res.headers.get('Content-Type') ?? 'application/octet-stream').split(';')[0].trim()
        const blob = await res.blob()

        if (cancelled) return

        // Route by content type. Office types get converted client-side; native browser
        // types get an object URL.
        if (contentType === OFFICE_DOCX || contentType === OFFICE_LEGACY_DOC) {
          const mammoth = await import('mammoth')
          const arrayBuffer = await blob.arrayBuffer()
          const result = await mammoth.convertToHtml({ arrayBuffer })
          if (!cancelled) setState({ kind: 'ready-html', html: result.value })
          return
        }
        if (contentType === OFFICE_XLSX || contentType === OFFICE_LEGACY_XLS) {
          const XLSX = await import('xlsx')
          const arrayBuffer = await blob.arrayBuffer()
          const workbook = XLSX.read(arrayBuffer, { type: 'array' })
          const parts: string[] = []
          for (const sheetName of workbook.SheetNames) {
            const sheet = workbook.Sheets[sheetName]
            parts.push(`<h3 style="font-family:inherit;color:#241F1D;margin:16px 0 8px">${escapeHtml(sheetName)}</h3>`)
            parts.push(XLSX.utils.sheet_to_html(sheet, { header: '', footer: '' }))
          }
          if (!cancelled) setState({ kind: 'ready-html', html: parts.join('') })
          return
        }
        // Native-previewable types get a blob URL.
        const url = URL.createObjectURL(blob)
        revokeUrl = url
        if (
          contentType.startsWith('image/') ||
          contentType.startsWith('text/') ||
          contentType === 'application/pdf'
        ) {
          if (!cancelled) setState({ kind: 'ready-native', url, contentType })
          return
        }
        if (contentType.startsWith('audio/')) {
          if (!cancelled) setState({ kind: 'ready-audio', url, contentType })
          return
        }
        if (contentType.startsWith('video/')) {
          if (!cancelled) setState({ kind: 'ready-video', url, contentType })
          return
        }
        // Genuinely unsupported (pptx, arbitrary binaries): tell the user honestly.
        if (revokeUrl) { URL.revokeObjectURL(revokeUrl); revokeUrl = null }
        if (!cancelled) setState({ kind: 'unsupported', contentType })
      } catch (e) {
        if (!cancelled) setState({ kind: 'error', message: String(e) })
      }
    }
    void load()

    return () => {
      cancelled = true
      if (revokeUrl) URL.revokeObjectURL(revokeUrl)
    }
  }, [doc.id])

  if (state.kind === 'loading') {
    return (
      <div className="flex items-center justify-center h-full text-helper text-sm">
        Loading preview…
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <div className="flex items-center justify-center h-full text-helper text-sm">
        Could not load preview: {state.message}
      </div>
    )
  }
  if (state.kind === 'ready-native') {
    if (state.contentType.startsWith('image/')) {
      return (
        <div className="flex items-center justify-center h-full p-6">
          <img src={state.url} alt={doc.filename} className="max-w-full max-h-full" />
        </div>
      )
    }
    return (
      <iframe
        src={state.url}
        title={doc.filename}
        className="w-full h-full bg-white"
      />
    )
  }
  if (state.kind === 'ready-html') {
    // The HTML comes from mammoth/xlsx — libraries that run on a file the student
    // uploaded to their own record. Not attacker-controlled the way an external feed
    // would be, but we still isolate it in its own container.
    // The `docx-preview-html` class carries explicit styles (colours, table borders,
    // headings) so it looks correct even without a `prose` typography plugin.
    return (
      <div className="w-full h-full overflow-auto bg-white text-[#241F1D]">
        <div
          className="docx-preview-html mx-auto"
          style={{
            maxWidth: '820px',
            padding: '48px 56px',
            fontFamily: 'ui-sans-serif, system-ui, sans-serif',
            fontSize: '11pt',
            lineHeight: 1.55,
            color: '#241F1D',
          }}
          dangerouslySetInnerHTML={{ __html: state.html }}
        />
      </div>
    )
  }
  if (state.kind === 'ready-audio') {
    return (
      <div className="flex items-center justify-center h-full p-6">
        <audio controls src={state.url} className="w-full max-w-lg" />
      </div>
    )
  }
  if (state.kind === 'ready-video') {
    return (
      <div className="flex items-center justify-center h-full p-6">
        <video controls src={state.url} className="max-w-full max-h-full" />
      </div>
    )
  }
  // unsupported
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-6 gap-2">
      <p className="text-sm font-medium">
        {friendlyTypeName(state.contentType)} — preview not available in the browser
      </p>
      <p className="text-helper text-sm max-w-sm">
        This file type ({state.contentType}) doesn't render inline.
        Download and open it in the relevant application.
      </p>
    </div>
  )
}

function friendlyTypeName(contentType: string): string {
  if (contentType === OFFICE_PPTX) return 'PowerPoint presentation'
  if (contentType.includes('presentation')) return 'Presentation'
  if (contentType === 'application/zip') return 'ZIP archive'
  return 'File'
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] ?? c
  })
}

// ---------- helpers

function isPreviewable(contentType: string): boolean {
  // "Try to preview" — for a couple of types the try lands on "unsupported" but the
  // reader still opens the modal, which is a better UX than a mysteriously-missing
  // button.
  return (
    contentType.startsWith('image/') ||
    contentType.startsWith('text/') ||
    contentType.startsWith('audio/') ||
    contentType.startsWith('video/') ||
    contentType === 'application/pdf' ||
    contentType === OFFICE_DOCX ||
    contentType === OFFICE_LEGACY_DOC ||
    contentType === OFFICE_XLSX ||
    contentType === OFFICE_LEGACY_XLS ||
    contentType === OFFICE_PPTX
  )
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
