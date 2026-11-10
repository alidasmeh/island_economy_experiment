import React, { useState, useEffect } from "react";
import { Container, Typography, Button } from "@mui/material";
import {
  FormControl,
  FormLabel,
  RadioGroup,
  FormControlLabel,
  Radio,
  Box,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { updateAccoutStatus } from "../components/updateAccountStatus";

function ConsentPage({ setUserId }) {
  const navigate = useNavigate();
  const [consent1, setConsent1] = useState("yes");
  const [consent2, setConsent2] = useState("yes");
  const [participantId, setParticipantId] = useState("");

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const participantIdQuery = searchParams.get("participant_id");
    if (participantIdQuery) {
      setParticipantId(participantIdQuery);
    } else {
      setParticipantId("-1");
    }
  }, [participantId]);

  const createAccount = async () => {
    if (participantId === "-1") return alert("participantId is not defined.");

    let baseUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

    const response = await fetch(`${baseUrl}/create_a_user/${participantId}`);
    const data = await response.json();
    if (data.status) {
      setUserId(data.user_id);
      if (await updateAccoutStatus(data.user_id, "account_is_created")) {
        navigate("/instruction");
      }
    } else {
      alert(data.error);
      console.log(response);
    }
  };

  return (
    <Container maxWidth="sm">
      <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
        Consent Page
      </Typography>

      <Typography variant="body1" gutterBottom>
        Read the text below and give us two YES.
      </Typography>

      <Typography variant="body1" gutterBottom>
        The text will be shown here!
      </Typography>

      <Typography variant="body1" gutterBottom>
        In addition, this ReactJS project is coupled with a FastAPI backend. You
        will find instances of WebSocket and RESTful calls in this project. The
        code of this call can be copy-pasted, too. Please make sure you update
        the backend app as well as the frontend.
      </Typography>

      <hr />
      <Box display="flex" flexDirection="column" gap={4} p={2}>
        <FormControl>
          <FormLabel>First Consent</FormLabel>
          <RadioGroup
            row
            value={consent1}
            onChange={(e) => setConsent1(e.target.value)}
          >
            <FormControlLabel value="yes" control={<Radio />} label="Yes" />
            <FormControlLabel value="no" control={<Radio />} label="No" />
          </RadioGroup>
        </FormControl>
        <FormControl>
          <FormLabel>Second Consent</FormLabel>
          <RadioGroup
            row
            value={consent2}
            onChange={(e) => setConsent2(e.target.value)}
          >
            <FormControlLabel value="yes" control={<Radio />} label="Yes" />
            <FormControlLabel value="no" control={<Radio />} label="No" />
          </RadioGroup>
        </FormControl>
      </Box>
      <Button
        variant="contained"
        color="success"
        onClick={createAccount}
        disabled={
          !consent1 || !consent2 || consent1 === "no" || consent2 === "no"
        }
      >
        Next
      </Button>
      <Button
        variant="contained"
        color="error"
        onClick={() => {
          navigate("prolific");
        }}
        sx={{ ml: 1 }}
      >
        Back to Prolific
      </Button>
    </Container>
  );
}

export default ConsentPage;
