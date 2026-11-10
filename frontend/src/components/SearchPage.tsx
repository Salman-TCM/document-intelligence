import { FormEvent, useState } from "react";
import { api, SearchHit } from "../api";

const EMPTY_FILTERS = {
  q: "",
  mode: "keyword",
  supplier: "",
  needs_review: "",
  date_from: "",
  date_to: "",
  min_total: "",
  max_total: "",
};

export default function SearchPage({ onOpen }: { onOpen: (documentId: string) => void }) {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof typeof EMPTY_FILTERS) => (e: { target: { value: string } }) =>
    setFilters({ ...filters, [key]: e.target.value });

  const search = async (e: FormEvent) => {
    e.preventDefault();
    const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== ""));
    try {
      setHits(await api.search(params));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <section className="panel">
      <form className="search-form" onSubmit={search}>
        <input className="query" placeholder="Search invoices, e.g. “cloud hosting” or INV-00012" value={filters.q} onChange={set("q")} />
        <select value={filters.mode} onChange={set("mode")}>
          <option value="keyword">Keyword</option>
          <option value="semantic">Semantic</option>
        </select>
        <button className="primary" type="submit">Search</button>

        <div className="filters">
          <input placeholder="Supplier" value={filters.supplier} onChange={set("supplier")} />
          <select value={filters.needs_review} onChange={set("needs_review")}>
            <option value="">Any review state</option>
            <option value="true">Needs review</option>
            <option value="false">OK</option>
          </select>
          <label>From <input type="date" value={filters.date_from} onChange={set("date_from")} /></label>
          <label>To <input type="date" value={filters.date_to} onChange={set("date_to")} /></label>
          <input type="number" placeholder="Min total" value={filters.min_total} onChange={set("min_total")} />
          <input type="number" placeholder="Max total" value={filters.max_total} onChange={set("max_total")} />
        </div>
      </form>

      {error && <p className="error">{error}</p>}
      {hits?.length === 0 && <p className="empty">No matching invoices.</p>}
      {hits && hits.length > 0 && (
        <table className="results">
          <thead>
            <tr>
              <th>Invoice</th><th>Date</th><th>Supplier</th><th>Total</th><th>File</th><th>Score</th><th></th>
            </tr>
          </thead>
          <tbody>
            {hits.map(({ invoice, filename, score }) => (
              <tr key={invoice.id} onClick={() => onOpen(invoice.document_id)}>
                <td>{invoice.data.invoice_number ?? "—"}</td>
                <td>{invoice.data.invoice_date ?? "—"}</td>
                <td>{invoice.data.supplier_name ?? "—"}</td>
                <td>{invoice.data.total != null ? `${invoice.data.total} ${invoice.data.currency ?? ""}` : "—"}</td>
                <td>{filename}</td>
                <td>{score != null ? score.toFixed(3) : ""}</td>
                <td>{invoice.needs_review && <span className="tag warn">review</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
