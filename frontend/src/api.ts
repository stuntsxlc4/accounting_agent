// Klient API backendu (FastAPI na localhost). Token przekazuje okno aplikacji w adresie.

const TOKEN_KEY = 'app-token'

function token(): string | null {
  const fromUrl = new URLSearchParams(window.location.search).get('token')
  if (fromUrl) {
    sessionStorage.setItem(TOKEN_KEY, fromUrl)
    window.history.replaceState(null, '', window.location.pathname)
    return fromUrl
  }
  return sessionStorage.getItem(TOKEN_KEY)
}

const appToken = token()

export class ApiError extends Error {}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (appToken) headers.set('X-App-Token', appToken)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(body?.detail ?? `Błąd serwera (${response.status})`)
  }
  return response.json() as Promise<T>
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export interface Status {
  configured: boolean
  error?: string
  nip?: string
  environment?: string
  certificate?: { name: string; valid_to: string; days_left: number }
  invoices_dir?: string
  statements_dir?: string
  current_month: string
  previous_month: string
}

export interface InvoiceFile {
  ksef_number: string
  issue_date: string
  number: string
  seller: string
  seller_nip: string
  gross: number
  currency: string
  invoice_type: string
  file_name: string
  downloaded: boolean
}

export interface MonthInvoices {
  month: string
  label: string
  folder: string
  invoices: InvoiceFile[]
}

export interface MonthStatements {
  month: string
  label: string
  folder: string
  files: { name: string; size: number }[]
  report: string | null
}

export interface Job<T = unknown> {
  id: string
  kind: string
  status: 'running' | 'done' | 'error'
  message: string
  done: number | null
  total: number | null
  log: string[]
  error: string | null
  result: T | null
}

export interface DebitRow {
  booking_date: string
  operation_date: string | null
  amount: number
  currency: string
  kind: string
  description: string
  invoice: { number: string; issue_date: string; seller: string; gross: number } | null
  method: string
  note: string
}

export interface UnpaidRow {
  issue_date: string
  number: string
  seller: string
  gross: number
  currency: string
  status: string
  details: string
}

export interface ReconcileResult {
  report: string
  statements: number
  unreadable: string[]
  invoice_count: number
  banks: { name: string; matched: DebitRow[]; missing: DebitRow[]; other: DebitRow[] }[]
  unpaid: UnpaidRow[]
}

export type OpenTarget = 'invoices_folder' | 'statements_folder' | 'invoice' | 'report'

export const api = {
  status: () => request<Status>('/api/status'),
  invoices: (month: string) => request<MonthInvoices>(`/api/invoices?month=${month}`),
  download: (month: string) => post<{ job_id: string }>('/api/invoices/download', { month }),
  statements: (month: string) => request<MonthStatements>(`/api/statements?month=${month}`),
  upload: (month: string, files: File[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    return request<MonthStatements>(`/api/statements/upload?month=${month}`, {
      method: 'POST',
      body: form,
    })
  },
  reconcile: (month: string) => post<{ job_id: string }>('/api/reconcile', { month }),
  testConnection: () => post<{ job_id: string }>('/api/ksef/test', {}),
  job: <T>(id: string) => request<Job<T>>(`/api/jobs/${id}`),
  open: (target: OpenTarget, month: string, name?: string) =>
    post<{ opened: string }>('/api/open', { target, month, name }),
}
