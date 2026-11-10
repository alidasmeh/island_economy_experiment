import React, { useEffect, useState } from "react";
import {
  Typography,
  Container,
  Box,
  RadioGroup,
  FormControl,
  FormControlLabel,
  Radio,
  TextField,
  Button,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { updateAccoutStatus } from "../components/updateAccountStatus";

function SurveyPage({ userId }) {
  const [responses, setResponses] = useState([
    { question: "favoriteLanguage", answer: "" },
    { question: "reason", answer: "" },
  ]);

  const [submitDisabled] = useState(false);
  const navigate = useNavigate();

  const updateResponse = (index, value) => {
    const newResponses = [...responses];
    newResponses[index].answer = value;
    setResponses(newResponses);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    let baseUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

    const update_survey_response = await fetch(`${baseUrl}/survey_update`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: `${userId}`,
        survey: responses,
        survey_title: "survey",
      }),
    });

    if (update_survey_response.ok) {
      const data = await update_survey_response.json();
      console.log("SurveyPage update_survey_response ", { data });

      if (await updateAccoutStatus(userId, "survey_is_over")) {
        navigate("/terminate/over");
      } else {
        console.log("there was an error to update db");
      }
    } else {
      console.log(
        "SurveyPage update_survey_response error",
        update_survey_response
      );
      return;
    }
    // console.log("Submitted responses:", responses);
  };

  useEffect(() => {
    updateAccoutStatus(userId, "survey_is_started");
    // eslint-disable-next-line 
  }, []);

  return (
    <Container maxWidth="sm">
      <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
        Survey
      </Typography>

      <Box component="form" onSubmit={handleSubmit}>
        <Box mb={3}>
          <Typography variant="h6">1. Question 1</Typography>
          <FormControl component="fieldset">
            <RadioGroup
              value={responses[0].answer}
              onChange={(e) => updateResponse(0, e.target.value)}
            >
              <FormControlLabel
                value="item1"
                control={<Radio />}
                label="Item 1"
              />
              <FormControlLabel
                value="item2"
                control={<Radio />}
                label="Item 2"
              />
              <FormControlLabel
                value="item3"
                control={<Radio />}
                label="Item 3"
              />
              <FormControlLabel
                value="item4"
                control={<Radio />}
                label="Item 4"
              />
            </RadioGroup>
          </FormControl>
        </Box>

        <Box mb={3}>
          <Typography variant="h6">2. Question 2</Typography>
          <TextField
            label="Explain your answer"
            multiline
            rows={3}
            value={responses[1].answer}
            onChange={(e) => updateResponse(1, e.target.value)}
            variant="outlined"
            sx={{ width: "100%" }}
          />
        </Box>

        <Button variant="contained" type="submit" disabled={submitDisabled}>
          Submit
        </Button>
      </Box>
    </Container>
  );
}

export default SurveyPage;
