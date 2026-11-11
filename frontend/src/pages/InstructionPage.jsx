// Stand-alone view of the participant instructions (for researchers to read and pilot).
// Participants see the same pages inside /play before the waiting room.
import React, { useEffect, useState } from "react";
import { Alert, CircularProgress, Container } from "@mui/material";
import { fetchRules } from "../game/api";
import Instructions from "../game/components/Instructions";

export default function InstructionPage() {
  const [rules, setRules] = useState(null);
  const [error, setError] = useState("");
  const condition = new URLSearchParams(window.location.search).get("condition") || "none";

  useEffect(() => {
    fetchRules().then(setRules).catch((e) => setError(e.message));
  }, []);

  return (
    <Container maxWidth="sm" sx={{ py: 2, px: 2 }}>
      {error && <Alert severity="error">{error}</Alert>}
      {!rules && !error && <CircularProgress sx={{ mt: 4 }} />}
      {rules && <Instructions rules={rules} condition={condition} doneLabel="End of instructions" />}
    </Container>
  );
}
