import React, { useEffect, useState } from "react";
import {
  Typography,
  Container,
  Box,
  Button,
  // TableContainer,
  // TableHead,
  // Table,
  // TableCell,
  // TableRow,
  // TableBody,
} from "@mui/material";
import { useParams } from "react-router-dom";

import PageTracker from "../components/PageTracker";

function ProjectPage() {
  const { userId } = useParams();

  const [userInfo, setUserInfo] = useState({});
  const [toShow, setToShow] = useState("status");

  const getUser = async (uesrId) => {
    let baseUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

    const response = await fetch(`${baseUrl}/dashboard/get_user/${userId}`);
    const data = await response.json();

    if (data.status) {
      setUserInfo(data.data);
      console.log(data.data);
    } else {
      alert(data.error);
      console.log(response);
    }
  };

  useEffect(() => {
    getUser(userId);
    // eslint-disable-next-line
  }, [userId]);

  return (
    <>
      <PageTracker
        arr={[
          {
            title: `User. #${userId}`,
            link: `/project/${userId}`,
            idToShow: "",
          },
        ]}
      />

      <Container maxWidth="md">
        <Typography variant="h4" gutterBottom sx={{ mt: 0 }}>
          User {userId}
        </Typography>
        <hr />
        <Typography variant="body1" gutterBottom sx={{}}>
          Participant id: {userInfo?.participant_id}
        </Typography>
        <Typography variant="body1" gutterBottom sx={{}}>
          Created at: {userInfo?.created_at}
        </Typography>

        <Box mt={5}>
          {["survey", "quiz", "status"].map((item, index) => {
            return (
              <Button
                variant="contained"
                onClick={() => {
                  setToShow(item);
                }}
                sx={{ mr: 1 }}
                key={index}
              >
                {item}
              </Button>
            );
          })}
        </Box>

        {toShow === "status" && (
          <Box sx={{ mb: 5 }}>
            <Typography variant="h5" gutterBottom sx={{ mt: 3 }}>
              Status
            </Typography>
            {userInfo?.status &&
              userInfo.status.map((item, index) => (
                <Typography key={index}>
                  - <b>{item.status}</b> : {item.updated_at}
                </Typography>
              ))}
          </Box>
        )}

        {toShow === "survey" && (
          <Box sx={{ mb: 5 }}>
            <Typography variant="h5" gutterBottom sx={{ mt: 3 }}>
              Survey
            </Typography>
            {userInfo?.surveys &&
              userInfo.surveys.survey.map((question, index) => {
                return (
                  <Box key={index}>
                    {question.question} : {question.answer}
                  </Box>
                );
              })}
          </Box>
        )}

        {toShow === "quiz" && (
          <Box sx={{ mb: 5 }}>
            <Typography variant="h5" gutterBottom sx={{ mt: 3 }}>
              Quiz
            </Typography>
            {userInfo?.surveys &&
              Object.entries(userInfo.surveys.quiz).map(([key, value]) => (
                <Typography key={key}>
                  - <b>{key}</b> : {value}
                </Typography>
              ))}
          </Box>
        )}

        {/* <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Word</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Reaction Time (ms)</TableCell>
                      <TableCell>Correct</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {userInfo?.experiment.experiment?.map((word, index) => (
                      <TableRow key={index}>
                        <TableCell>{word.word.word}</TableCell>
                        <TableCell>
                          {word.word.isWord ? "Word" : "Non-word"}
                        </TableCell>
                        <TableCell>{parseInt(word.rt)} ms</TableCell>
                        <TableCell>{word.isCorrect ? "Yes" : "No"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer> */}
      </Container>
    </>
  );
}

export default ProjectPage;
