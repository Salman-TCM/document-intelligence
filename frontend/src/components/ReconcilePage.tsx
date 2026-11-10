import { useEffect, useState } from "react";
import { api, DocumentSummary, ReconcileResult } from "../api";

const format = (value: unknown) => (value == null ? "—" : String(value));

export default function ReconcilePage() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [result, setResult] = useState<ReconcileResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listDocuments()
      .then((docs) => setDocuments(docs.filter((d) => d.status === "done")))
      .catch((e) => setError(e.message));
  }, []);

  const compare = async () => {
    try {
      setResult(await api.reconcile(left, right));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const picker = (value: string, onChange: (id: string) => void) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose a document…</option>
      {documents.map((d) => (
        <option key={d.id} value={d.id}>{d.filename} ({d.invoice_count})</option>
      ))}
    </select>
  );

  return (
    <section className="panel">
      <p className="hint">Match invoices between two documents by invoice number, e.g. a PDF batch against the Excel register.</p>
      <div className="reconcile-form">
        {picker(left, setLeft)}
        <span>vs</span>
        {picker(right, setRight)}
        <button className="primary" disabled={!left || !right} onClick={compare}>Compare</button>
      </div>
      {error && <p className="error">{error}</p>}

      {result && (
        <>
          <h3>Matched ({result.matched.length})</h3>
          <table className="results">
            <thead>
              <tr><th>Invoice</th><th>Field</th><th>Left</th><th>Right</th></tr>
            </thead>
            <tbody>
              {result.matched.map((match) =>
                match.differences.length === 0 ? (
                  <tr key={match.invoice_number}>
                    <td>{match.invoice_number}</td>
                    <td colSpan={3}><span className="tag ok">all fields match</span></td>
                  </tr>
                ) : (
                  match.differences.map((diff) => (
                    <tr key={match.invoice_number + diff.field} className="mismatch">
                      <td>{match.invoice_number}</td>
                      <td>{diff.field}</td>
                      <td>{format(diff.left)}</td>
                      <td>{format(diff.right)}</td>
                    </tr>
                  ))
                ),
              )}
            </tbody>
          </table>
          <h3>Only in left ({result.only_in_left.length})</h3>
          <p>{result.only_in_left.join(", ") || "—"}</p>
          <h3>Only in right ({result.only_in_right.length})</h3>
          <p>{result.only_in_right.join(", ") || "—"}</p>
        </>
      )}
    </section>
  );
}
