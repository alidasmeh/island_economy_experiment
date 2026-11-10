import React, { useState, useEffect } from "react";
import { Container, Typography, Box, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";
import Snackbar from "@mui/material/Snackbar";
import Slide from "@mui/material/Slide";
import Fade from "@mui/material/Fade";

function QuizPage() {
  const navigate = useNavigate();
  const delayBetweenQuestions = 3000;
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [numberOfWrongAnswer, setNumberOfWrongAnswer] = useState(0);
  const [numberOfWrongRounds, setNumberOfWrongRounds] = useState([0, 0, 0]);
  const [roundNumber, setRoundNumber] = useState(0);
  const [numberOfCorrectAnswers, setNumberOfCorrectAnswers] = useState(0);
  const [snackbarOpenStatus, setSnackbarOpenStatus] = useState({
    open: false,
    Transition: Fade,
    color: "#4caf50",
    text: "",
  });
  const [selectedOptionInCurrentQuestion, setSelectedOptionInCurrentQuestion] =
    useState(-1);

  const [temporaryCurrentQuestionIndex, setTemporaryCurrentQuestionIndex] =
    useState();

  const [disableOptions, setDisableOptions] = useState(false);

  const goToNextStep = () => {
    if (
      roundNumber === 2 &&
      numberOfWrongRounds[0] === 1 &&
      numberOfWrongRounds[1] === 1 &&
      numberOfWrongRounds[2] === 1
    ) {
      
      window.alert(
        "You have the failed the quiz three times and will be redirected to Prolific."
      );
    } else {
      
      navigate("/game");
    }
  };

  const selectOption = (currentQuestionIndex, optionIndex) => {
    if (disableOptions) return;
    setSelectedOptionInCurrentQuestion(optionIndex);
    setTemporaryCurrentQuestionIndex(currentQuestionIndex);
  };

  const submitAnswer = () => {
    setDisableOptions(true);
    let localNumberOfCurrectAnswer = numberOfCorrectAnswers;

    // check the answer
    let color = "#2e7d32";
    let text = "Correct.";
    if (
      questionsList[temporaryCurrentQuestionIndex]["options"][
        selectedOptionInCurrentQuestion
      ].isTrue === false
    ) {
      color = "#d32f2f";
      setNumberOfWrongAnswer(numberOfWrongAnswer + 1);
      text = `Wrong Answer.`;
      const temp = [...numberOfWrongRounds];
      temp[roundNumber] = 1;
      setNumberOfWrongRounds(temp);
    } else {
      setNumberOfCorrectAnswers(numberOfCorrectAnswers + 1);
      localNumberOfCurrectAnswer++;
    }

    handleOpenSnackbar(color, text);

    setTimeout(() => {
      const nextQuestion = currentQuestion + 1;
      if (
        (nextQuestion >= questionsList.length &&
          localNumberOfCurrectAnswer === questionsList.length) ||
        (roundNumber === 2 &&
          numberOfWrongRounds[0] === 1 &&
          numberOfWrongRounds[1] === 1 &&
          numberOfWrongRounds[2] === 1)
      ) {
        // it means that person tried 3 rounds and could not respond 3 questions correctly consecutively
        return goToNextStep();
      } else if (
        nextQuestion >= questionsList.length &&
        localNumberOfCurrectAnswer < questionsList.length
      ) {
        // go to first question for the nex try
        setNumberOfCorrectAnswers(0);
        setSelectedOptionInCurrentQuestion(-1);
        setDisableOptions(false);
        setCurrentQuestion(0);
        setRoundNumber(roundNumber + 1);
        handleOpenSnackbar("#1976d2", "You see the list of questions again.");
      } else {
        // go to next question
        setSelectedOptionInCurrentQuestion(-1);
        setCurrentQuestion(nextQuestion);
        setDisableOptions(false);
      }
    }, 3000);
  };

  useEffect(() => {
    console.log("numberOfWrongRounds", numberOfWrongRounds);
  }, [numberOfWrongRounds]);

  const handleOpenSnackbar = (color, text) => {
    function SlideTransition(props) {
      return <Slide {...props} direction="down" />;
    }
    setSnackbarOpenStatus({
      open: true,
      Transition: SlideTransition,
      text,
      color,
    });
  };
  const handleCloseSnackbar = () => {
    setSnackbarOpenStatus({
      ...snackbarOpenStatus,
      open: false,
      text: "",
    });
  };

  return (
    <Container maxWidth="sm">
      <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
        Quiz
      </Typography>

      <Snackbar
        open={snackbarOpenStatus.open}
        anchorOrigin={{ vertical: "top", horizontal: "center" }}
        slots={{ transition: snackbarOpenStatus.Transition }}
        message={snackbarOpenStatus.text}
        key={snackbarOpenStatus.Transition.name}
        autoHideDuration={delayBetweenQuestions - 500}
        onClose={handleCloseSnackbar}
        ContentProps={{
          sx: {
            backgroundColor: snackbarOpenStatus.color,
            color: "#fff",
          },
        }}
      />

      <Box>
        <Typography variant="body1" gutterBottom sx={{ color: "gray" }}>
          Question #{currentQuestion + 1}
        </Typography>
        <Typography
          variant="body1"
          gutterBottom
          sx={{ fontSize: 22 }}
          dangerouslySetInnerHTML={{
            __html: questionsList[currentQuestion].question,
          }}
        />

        {questionsList[currentQuestion]["options"].map((option, index) => (
          <Typography
            key={`currentQuestion${currentQuestion}option${index}`}
            variant="body1"
            gutterBottom
            sx={{
              fontSize: 18,
              padding: "12px 18px",
              borderRadius: "3px",
              transition: "all 0.3s",
              cursor: disableOptions ? "" : "pointer",
              background:
                index === selectedOptionInCurrentQuestion ? "#aeaeae" : "#eee",
              "&:hover": {
                background:
                  selectedOptionInCurrentQuestion !== -1 ? "" : "#aeaeae",
              },
            }}
            onClick={() => {
              selectOption(currentQuestion, index);
            }}
          >
            {option.text}
          </Typography>
        ))}

        <Box>
          <Button
            variant="contained"
            color="success"
            onClick={() => {
              submitAnswer(true);
            }}
            disabled={!(selectedOptionInCurrentQuestion > -1) || disableOptions}
          >
            Submit
          </Button>
        </Box>
      </Box>
    </Container>
  );
}

export default QuizPage;

const questionsList = [
  {
    question:
      `<p>Q1 is here?!</p>`,
    options: [
      {
        text: "option 1",
        isTrue: false,
      },
      {
        text: "Option 2",
        isTrue: false,
      },
      {
        text: "True",
        isTrue: true,
      },
    ],
  },
  {
    question:
      "Q2 is here?!",
    options: [
      {
        text: "option 1",
        isTrue: false,
      },
      {
        text: "True",
        isTrue: true,
      },
    ],
  },
];
