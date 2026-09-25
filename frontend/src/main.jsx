// Minimal shell so `docker compose up` serves something end to end.
// The real dashboard (Leads, Company detail, Configuration, Runs) is GIG-33..37.
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function App() {
  const [leads, setLeads] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    fetch(`${API}/leads`)
      .then((r) => r.json())
      .then(setLeads)
      .catch((e) => setError(String(e)));
  }, []);
  return (
    <main style={{ fontFamily: "system-ui", padding: 24 }}>
      <h1>Orange Signals</h1>
      <p>
        API: <a href={`${API}/docs`}>{API}/docs</a>
      </p>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
      <table cellPadding={6}>
        <thead>
          <tr><th align="left">Company</th><th align="left">Service</th><th>Tier</th><th>Score</th><th align="left">Why now</th></tr>
        </thead>
        <tbody>
          {leads.map((l) => (
            <tr key={l.lead_id}>
              <td>{l.company}</td><td>{l.service}</td><td>{l.tier}</td><td>{l.final_score}</td><td>{l.summary}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
