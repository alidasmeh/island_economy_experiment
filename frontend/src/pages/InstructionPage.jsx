// Stand-alone view of the participant instructions (for researchers to read and pilot).
// Participants see the same pages inside /play before the waiting room. Nothing is recorded here.
//   /instruction?condition=none                     no coordinator
//   /instruction?condition=human                    coordinator condition, islander
//   /instruction?condition=human&role=coordinator   coordinator condition, coordinator
import React, { useEffect, useState } from "react";
import { Alert, CircularProgress, Container, ToggleButton, ToggleButtonGroup } from "@mui/material";
import { fetchRules } from "../game/api";
import Instructions from "../game/components/Instructions";

const VERSIONS = {
  none: { condition: "none", role: "player", label: "No coordinator" },
  human: { condition: "human", role: "player", label: "Islander (with coordinator)" },
  coordinator: { condition: "human", role: "coordinator", label: "Coordinator" },
};

function initialVersion() {
  const q = new URLSearchParams(window.location.search);
  if (q.get("role") === "coordinator") return "coordinator";
  return q.get("condition") === "human" ? "human" : "none";
}

export default function InstructionPage() {
  const [rules, setRules] = useState(null);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(initialVersion);
  const v = VERSIONS[version];

  useEffect(() => {
    fetchRules().then(setRules).catch((e) => setError(e.message));
  }, []);

  const choose = (_e, next) => {
    if (!next) return;
    setVersion(next);
    const q = new URLSearchParams({ condition: VERSIONS[next].condition });
    if (VERSIONS[next].role === "coordinator") q.set("role", "coordinator");
    window.history.replaceState(null, "", `?${q}`);
  };

  return (
    <Container maxWidth="sm" sx={{ py: 2, px: 2 }}>
      <ToggleButtonGroup exclusive size="small" fullWidth value={version} onChange={choose} sx={{ mb: 2 }}
        aria-label="Which instructions to preview">
        {Object.entries(VERSIONS).map(([k, x]) => (
          <ToggleButton key={k} value={k} sx={{ textTransform: "none" }}>{x.label}</ToggleButton>
        ))}
      </ToggleButtonGroup>
      {error && <Alert severity="error">{error}</Alert>}
      {!rules && !error && <CircularProgress sx={{ mt: 4 }} />}
      {rules && (
        <Instructions key={version} rules={rules} condition={v.condition} role={v.role}
          doneLabel="End of instructions" />
      )}
    </Container>
  );
}
