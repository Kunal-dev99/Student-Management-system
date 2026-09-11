import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

/**
 * "under_assessment" → "Under Assessment".
 * "pass_with_corrections" → "Pass With Corrections".
 * Preserves acronyms of length 2-4 that are all-caps in the input (e.g. "PhD", "HR").
 */
export function titleCase(input: string | null | undefined): string {
  if (input == null || input === '') return ''
  return String(input)
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((w) => (
      // Keep 2-4 letter ACRONYMS (PhD, HR, ICR) as-is.
      /^[A-Z]{2,4}$/.test(w) || /^[A-Z][a-z]*[A-Z]/.test(w)
        ? w
        : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()
    ))
    .join(' ')
}

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    draft: 'status-draft',
    staged: 'status-building',
    testing: 'status-testing',
    test_passed: 'status-published',
    test_failed: 'status-failed',
    published: 'status-published',
    failed: 'status-failed',
  }
  return colors[status] || 'status-draft'
}

export function formatXml(xml: string): string {
  try {
    const PADDING = '  '
    let formatted = ''
    let pad = 0
    
    xml.split(/>\s*</).forEach((node) => {
      if (node.match(/^\/\w/)) pad -= 1
      formatted += PADDING.repeat(pad) + '<' + node + '>\n'
      if (node.match(/^<?\w[^>]*[^\/]$/)) pad += 1
    })
    
    return formatted.substring(1, formatted.length - 2)
  } catch {
    return xml
  }
}





















