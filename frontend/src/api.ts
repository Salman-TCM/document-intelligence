export type Status = "queued" | "processing" | "done" | "failed";

export interface LineItem {
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
}

export interface InvoiceData {
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_name: string | null;
  customer_name: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  currency: string | null;
  line_items: LineItem[];
  uncertain_fields: string[];
}

export interface ValidationIssue {
  code: string;
  field: string;
  message: string;
}

export interface Invoice {
  id: string;
  document_id: string;
  position: number;
  source: string | null;
  data: InvoiceData;
  validation_errors: ValidationIssue[];
  needs_review: boolean;
  corrected: boolean;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  status: Status;
  error: string | null;
  page_count: number | null;
  processing_ms: number | null;
  created_at: string;
  invoice_count: number;
  needs_review: boolean;
}

export interface DocumentDetail extends DocumentSummary {
  invoices: Invoice[];
  events: { stage: string; message: string; created_at: string }[];
}

export interface SearchHit {
  invoice: Invoice;
  filename: string;
  score: number | null;
}

export interface ReconcileResult {
  matched: { invoice_number: string; differences: { field: string; left: unknown; right: unknown }[] }[];
  only_in_left: string[];
  only_in_right: string[];
}

const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : response.statusText);
  }
  return response;
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await request(path, init);
  return response.json() as Promise<T>;
}

export const api = {
  listDocuments: () => getJson<DocumentSummary[]>("/documents"),

  getDocument: (id: string) => getJson<DocumentDetail>(`/documents/${id}`),

  upload: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return getJson<DocumentSummary[]>("/documents", { method: "POST", body: form });
  },

  reprocess: (id: string) => getJson<DocumentSummary>(`/documents/${id}/reprocess`, { method: "POST" }),

  correctInvoice: (id: string, changes: Partial<InvoiceData>) =>
    getJson<Invoice>(`/invoices/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),

  search: (params: Record<string, string>) => getJson<SearchHit[]>(`/search?${new URLSearchParams(params)}`),

  reconcile: (left: string, right: string) =>
    getJson<ReconcileResult>(`/reconcile?${new URLSearchParams({ left, right })}`),

  // Fetched as a blob so the API key header is sent too.
  openOriginal: async (id: string) => {
    const blob = await (await request(`/documents/${id}/file`)).blob();
    window.open(URL.createObjectURL(blob), "_blank");
  },
};
