import React, { useState } from "react";
import { Container, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { ListItem, ListItemText, Box } from "@mui/material";
import { updateAccoutStatus } from "../components/updateAccountStatus";

function InstructionPage({ userId }) {
  const navigate = useNavigate();

  const [currentSlide, setCurrentSlide] = useState(0);
  const [currentBullet, setCurrentBullet] = useState(1);

  const goToSlide = (direction) => {
    if (direction === "next") {
      const theNextBullet = currentBullet + 1;
      if (theNextBullet <= instructionObject[currentSlide].length) {
        setCurrentBullet(theNextBullet);
        return;
      }

      const theNextSlide = currentSlide + 1;
      if (theNextSlide <= instructionObject.length - 1) {
        setCurrentSlide(theNextSlide);
        setCurrentBullet(1);
        return;
      }
    } else {
      if (currentSlide === 0 && currentBullet === 1) return;

      const theNextBullet = currentBullet - 1;
      if (theNextBullet <= 0) {
        setCurrentSlide(currentSlide - 1);
        setCurrentBullet(instructionObject[currentSlide - 1].length);
        return;
      } else {
        setCurrentBullet(theNextBullet);
        return;
      }
    }
  };

  const gotToNextStep = async () => {
    if (await updateAccoutStatus(userId, "instruction_is_over")) {
      navigate("/quiz");
    }
  };

  return (
    <Container maxWidth="sm" sx={{ mt: 5 }}>
      {/* <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
        Instruction
      </Typography> */}
      <Box
        gap={4}
        p={1}
        sx={{ minHeight: 550, background: "#eee", borderRadius: 2, px: 2 }}
      >
        {instructionObject[currentSlide]
          .slice(0, currentBullet)
          .map((item, idx) => (
            <ListItem key={idx}>
              <ListItemText
                primary={
                  <div
                    style={{ fontSize: "1.1rem" }}
                    dangerouslySetInnerHTML={{ __html: item }}
                  />
                }
              />
            </ListItem>
          ))}
      </Box>
      <Box gap={4} p={2}>
        <Button
          variant="contained"
          color="primary"
          onClick={() => goToSlide("prev")}
          disabled={currentSlide === 0 && currentBullet === 1}
        >
          Previous
        </Button>
        {!(
          currentSlide === instructionObject.length - 1 &&
          currentBullet ===
            instructionObject[instructionObject.length - 1].length
        ) && (
          <Button
            variant="contained"
            color="primary"
            sx={{ ml: 1 }}
            onClick={() => goToSlide("next")}
          >
            Next
          </Button>
        )}

        {currentSlide === instructionObject.length - 1 &&
          currentBullet ===
            instructionObject[instructionObject.length - 1].length && (
            <Button
              variant="contained"
              sx={{ ml: 1 }}
              color="success"
              onClick={() => gotToNextStep()}
            >
              Go To Next Page
            </Button>
          )}
      </Box>
    </Container>
  );
}

export default InstructionPage;

const instructionObject = [
  [
    `<h2>Welcome to the investment game!</h2>`,
    `<li>You will play 5 rounds of the investment game</li>`,
    `<li>Every 100 points you earn in the game will earn you £1 as a bonus payment!</li>`,
  ],
];
