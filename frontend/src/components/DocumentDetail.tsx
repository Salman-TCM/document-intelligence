import { useEffect, useState } from "react";
import { api, DocumentDetail, Status } from "../api";
import InvoiceCard from "./InvoiceCard";
import StatusBadge from "./StatusBadge";

interface Props {
  id: string;
  status?: Status; // from the polled list, so we reload when processing finishes
  onChange: () => void;
}

export default function DocumentDetailView({ id, status, onChange }: Props) {
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => api.getDocument(id).then(setDoc).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, [id, status]);

  const reprocess = async () => {
    try {
      await api.reprocess(id);
      onChange();
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  if (error) return <p className="error">{error}</p>;
  if (!doc) return <p className="empty">Loading…</p>;

  const canReprocess = doc.status === "done" || doc.status === "failed";

  return (
    <div>
      <div className="detail-header">
        <div>
          <h2>{doc.filename}</h2>
          <div className="doc-meta">
            <StatusBadge status={doc.status} />
            {doc.page_count != null && <span>{doc.page_count} page(s)</span>}
            {doc.processing_ms != null && <span>{(doc.processing_ms / 1000).toFixed(1)}s</span>}
          </div>
        </div>
        <div className="actions">
          <button onClick={() => api.openOriginal(doc.id)}>View original</button>
          {canReprocess && <button onClick={reprocess}>Reprocess</button>}
        </div>
      </div>

      {doc.error && <p className="error">{doc.error}</p>}

      {doc.invoices.map((invoice) => (
        <InvoiceCard key={invoice.id} invoice={invoice} onSaved={() => { load(); onChange(); }} />
      ))}
      {doc.status === "done" && doc.invoices.length === 0 && <p className="empty">No invoices found in this file.</p>}

      <h3>History</h3>
      <ol className="events">
        {doc.events.map((event, i) => (
          <li key={i}>
            <time>{new Date(event.created_at).toLocaleTimeString()}</time>
            <strong>{event.stage}</strong> {event.message}
          </li>
        ))}
      </ol>
    </div>
  );
}
