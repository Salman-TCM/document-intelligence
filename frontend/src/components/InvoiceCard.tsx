import { useState } from "react";
import { api, Invoice, InvoiceData } from "../api";

type EditableField = Exclude<keyof InvoiceData, "line_items" | "uncertain_fields">;

const FIELDS: { key: EditableField; label: string; numeric?: boolean }[] = [
  { key: "invoice_number", label: "Invoice number" },
  { key: "invoice_date", label: "Invoice date" },
  { key: "supplier_name", label: "Supplier" },
  { key: "customer_name", label: "Customer" },
  { key: "subtotal", label: "Subtotal", numeric: true },
  { key: "tax", label: "Tax", numeric: true },
  { key: "total", label: "Total", numeric: true },
  { key: "currency", label: "Currency" },
];

function toFormValues(data: InvoiceData) {
  return Object.fromEntries(FIELDS.map(({ key }) => [key, data[key]?.toString() ?? ""]));
}

export default function InvoiceCard({ invoice, onSaved }: { invoice: Invoice; onSaved: () => void }) {
  const { data } = invoice;
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState(() => toFormValues(data));
  const [error, setError] = useState<string | null>(null);

  const fieldsWithIssues = new Set(invoice.validation_errors.map((issue) => issue.field));

  const save = async () => {
    // Send only what the reviewer actually changed.
    const original = toFormValues(data);
    const changes: Record<string, string | number | null> = {};
    for (const { key, numeric } of FIELDS) {
      if (values[key] === original[key]) continue;
      const value = values[key].trim();
      changes[key] = value === "" ? null : numeric ? Number(value) : value;
    }
    if (Object.keys(changes).length === 0) return setEditing(false);

    try {
      await api.correctInvoice(invoice.id, changes as Partial<InvoiceData>);
      setEditing(false);
      setError(null);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <article className={`invoice ${invoice.needs_review ? "review" : ""}`}>
      <header>
        <h3>
          Invoice {invoice.position + 1}
          {invoice.source && <small> · {invoice.source}</small>}
        </h3>
        <div className="actions">
          {invoice.corrected && <span className="tag">corrected</span>}
          {invoice.needs_review ? <span className="tag warn">needs review</span> : <span className="tag ok">ok</span>}
          {editing ? (
            <>
              <button onClick={() => setEditing(false)}>Cancel</button>
              <button className="primary" onClick={save}>Save</button>
            </>
          ) : (
            <button onClick={() => { setValues(toFormValues(data)); setEditing(true); }}>Edit</button>
          )}
        </div>
      </header>

      {invoice.validation_errors.length > 0 && (
        <ul className="issues">
          {invoice.validation_errors.map((issue, i) => (
            <li key={i}>{issue.message}</li>
          ))}
        </ul>
      )}
      {error && <p className="error">{error}</p>}

      <dl className="fields">
        {FIELDS.map(({ key, label }) => (
          <div key={key} className={fieldsWithIssues.has(key) ? "flagged" : ""}>
            <dt>{label}</dt>
            <dd>
              {editing ? (
                <input value={values[key]} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
              ) : (
                data[key] ?? <span className="missing">—</span>
              )}
            </dd>
          </div>
        ))}
      </dl>

      {data.line_items.length > 0 && (
        <table>
          <thead>
            <tr><th>Description</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr>
          </thead>
          <tbody>
            {data.line_items.map((item, i) => (
              <tr key={i}>
                <td>{item.description}</td>
                <td>{item.quantity}</td>
                <td>{item.unit_price}</td>
                <td>{item.amount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  );
}
