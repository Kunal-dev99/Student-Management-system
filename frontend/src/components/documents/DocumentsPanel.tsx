'use client'

import { useRef, useState } from 'react'
import { FileText, Download, Trash2, Upload } from 'lucide-react'
import { PageSection } from '@/components/common/PageSection'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import {
  useDocuments, useUploadDocument, useDeleteDocument, downloadDocument,
  type DocumentItem,
} from '@/features/documents/api'

function humanSize(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let n = bytes / 1024
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return `${n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`
}

interface DocumentsPanelProps {
  ownerType: string
  ownerId: string
  docType?: string
  title?: string
}

export function DocumentsPanel({ ownerType, ownerId, docType, title = 'Documents' }: DocumentsPanelProps) {
  const { toast } = useToast()
  const { data, isLoading } = useDocuments(ownerType, ownerId)
  const upload = useUploadDocument()
  const remove = useDeleteDocument()
  const fileRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [type, setType] = useState(docType ?? '')

  const err = (e: unknown) => toast({ title: 'Action failed', description: (e as Error).message, variant: 'destructive' })

  const doUpload = async () => {
    if (!file) return
    try {
      await upload.mutateAsync({ ownerType, ownerId, docType: type || undefined, file })
      toast({ title: 'Document uploaded', description: file.name })
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (e) { err(e) }
  }

  const doDelete = async (doc: DocumentItem) => {
    try {
      await remove.mutateAsync({ id: doc.id, ownerType, ownerId })
      toast({ title: 'Document deleted', description: doc.filename })
    } catch (e) { err(e) }
  }

  return (
    <PageSection icon={FileText} title={title} accent="primary">
      {isLoading ? <Skeleton className="h-16 w-full" /> : (
        <div className="space-y-2 mb-4">
          {data && data.length > 0 ? data.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between gap-3 border-b border-border/60 last:border-0 pb-2 last:pb-0">
              <div className="flex items-center gap-2 min-w-0 flex-wrap">
                <span className="text-sm font-medium truncate">{doc.filename}</span>
                {doc.docType && <Badge variant="secondary">{doc.docType}</Badge>}
                {doc.scanStatus && doc.scanStatus !== 'clean' && (
                  <Badge variant={doc.scanStatus === 'infected' ? 'destructive' : 'warning'}>{doc.scanStatus}</Badge>
                )}
                <span className="text-helper num">{humanSize(doc.sizeBytes)}</span>
                <span className="text-helper num">{doc.createdAt?.slice(0, 10)}</span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => downloadDocument(doc)} aria-label="Download">
                  <Download className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="ghost" disabled={remove.isPending} onClick={() => doDelete(doc)} aria-label="Delete">
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )) : <p className="text-helper">No documents uploaded yet.</p>}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 pt-2 border-t border-border">
        <Input
          ref={fileRef}
          type="file"
          className="w-64 h-9"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {!docType && (
          <Input
            placeholder="Type (optional)"
            className="w-40 h-9"
            value={type}
            onChange={(e) => setType(e.target.value)}
          />
        )}
        <Button size="sm" disabled={!file || upload.isPending} onClick={doUpload}>
          <Upload className="h-4 w-4 mr-1.5" />
          {upload.isPending ? 'Uploading…' : 'Upload'}
        </Button>
      </div>
    </PageSection>
  )
}
