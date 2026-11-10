import { useState } from "react";
import DocumentsPage from "./components/DocumentsPage";
import ReconcilePage from "./components/ReconcilePage";
import SearchPage from "./components/SearchPage";

type Tab = "documents" | "search" | "reconcile";

export default function App() {
  const [tab, setTab] = useState<Tab>("documents");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const openDocument = (id: string) => {
    setSelectedId(id);
    setTab("documents");
  };

  return (
    <>
      <header className="topbar">
        <h1>Document Intelligence</h1>
        <nav>
          {(["documents", "search", "reconcile"] as Tab[]).map((name) => (
            <button key={name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}>
              {name[0].toUpperCase() + name.slice(1)}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {tab === "documents" && <DocumentsPage selectedId={selectedId} onSelect={setSelectedId} />}
        {tab === "search" && <SearchPage onOpen={openDocument} />}
        {tab === "reconcile" && <ReconcilePage />}
      </main>
    </>
  );
}
