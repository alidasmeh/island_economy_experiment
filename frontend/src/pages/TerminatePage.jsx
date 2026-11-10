import React, { useEffect } from "react";
import { useParams } from "react-router-dom";

import { Container, Typography } from "@mui/material";
import { updateAccoutStatus } from "../components/updateAccountStatus";

export default function TerminatePage({ userId }) {
  const { status } = useParams();

  useEffect(() => {
    updateAccoutStatus(userId, `terminate_page_with_status_${status}`);
    // eslint-disable-next-line 
  }, []);

  useEffect(() => {
    setTimeout(() => {
      // window.location.href = "http://prolific.com/?over";
      alert("Go to prolific")
    }, 1000);
  });
  return (
    <Container maxWidth="sm" sx={{ mt: 5, mb: 5 }}>
      <Typography variant="h4" gutterBottom>
        Terminate Page
      </Typography>

      {status === "neutral" && (
        <Typography>You are neutral! We have nothing to ask you!</Typography>
      )}
      {status === "over" && (
        <Typography>Thank you for participation.</Typography>
      )}
      {status === "failed" && (
        <Typography>You could not pass the quiz.</Typography>
      )}
    </Container>
  );
}
