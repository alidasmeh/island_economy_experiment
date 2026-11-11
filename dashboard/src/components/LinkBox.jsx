// The participant link and the Prolific study URL for a session, each with a copy button.
import React, { useState } from "react";
import { Button, Stack, TextField, Typography } from "@mui/material";
import { participantLink, prolificLink } from "../api";

function CopyField({ label, value, help }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard not available: the field can still be selected by hand */
    }
  };
  return (
    <>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
        <TextField
          label={label}
          value={value}
          size="small"
          fullWidth
          InputProps={{ readOnly: true, sx: { fontFamily: "monospace", fontSize: 13 } }}
          onFocus={(e) => e.target.select()}
        />
        <Button variant="outlined" size="small" onClick={copy} sx={{ minWidth: 80 }}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </Stack>
      {help && (
        <Typography variant="caption" color="text.secondary">
          {help}
        </Typography>
      )}
    </>
  );
}

export function LinkBox({ code }) {
  return (
    <>
      <CopyField label="Participant link (for testing)" value={participantLink(code)} />
      <CopyField
        label="Study URL for Prolific"
        value={prolificLink(code)}
        help="Paste into Prolific with “URL parameters” chosen; Prolific fills in the {{%…%}} parts."
      />
    </>
  );
}
