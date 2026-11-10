import { useCallback, useEffect, useState } from "react";
import { api, DocumentSummary } from "../api";
import DocumentDetailView from "./DocumentDetail";
import StatusBadge from "./StatusBadge";

const ACCEPTED = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.xlsx,.xls,.csv";
const POLL_MS = 2000;

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export default function DocumentsPage({ selectedId, onSelect }: Props) {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.listDocuments().then(setDocuments).catch((e) => setError(e.message));
  }, []);

  useEffect(refresh, [refresh]);

  // Keep polling while anything is still in the queue.
  const busy = documents.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [busy, refresh]);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setError(null);
    try {
      await api.upload(Array.from(files));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const selected = documents.find((d) => d.id === selectedId);

  return (
    <div className="split">
      <section className="panel">
        <label
          className="dropzone"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            upload(e.dataTransfer.files);
          }}
        >
          <input type="file" multiple accept={ACCEPTED} onChange={(e) => upload(e.target.files)} hidden />
          {uploading ? "Uploading…" : "Drop files here or click to upload"}
          <small>PDF, JPG, PNG, TIFF, XLSX, XLS, CSV</small>
        </label>
        {error && <p className="error">{error}</p>}

        <ul className="doc-list">
          {documents.map((doc) => (
            <li key={doc.id} className={doc.id === selectedId ? "selected" : ""} onClick={() => onSelect(doc.id)}>
              <div className="doc-name">{doc.filename}</div>
              <div className="doc-meta">
                <StatusBadge status={doc.status} />
                {doc.status === "done" && <span>{doc.invoice_count} invoice(s)</span>}
                {doc.needs_review && <span className="tag warn">needs review</span>}
              </div>
            </li>
          ))}
          {documents.length === 0 && <li className="empty">No documents yet</li>}
        </ul>
      </section>

      <section className="panel grow">
        {selectedId ? (
          <DocumentDetailView key={selectedId} id={selectedId} status={selected?.status} onChange={refresh} />
        ) : (
          <p className="empty">Select a document to see what was extracted.</p>
        )}
      </section>
    </div>
  );
}
