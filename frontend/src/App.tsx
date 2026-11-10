import { useState } from "react";
import DocumentsPage from "./components/DocumentsPage";

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <>
      <header className="topbar">
        <h1>Document Intelligence</h1>
      </header>
      <main>
        <DocumentsPage selectedId={selectedId} onSelect={setSelectedId} />
      </main>
    </>
  );
}
