import React, { useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import CustomizedTheme from "./theme";
// import Header from "./components/Header";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

import ConsentPage from "./pages/ConsentPage";
import InstructionPage from "./pages/InstructionPage";
import GamePage from "./pages/GamePage";
import SurveyPage from "./pages/SurveyPage";
// import QuizPage from "./pages/QuizPage";
import QuizPage from "./pages/QuizPageVersionTwo";
import TerminatePage from "./pages/TerminatePage";

function App() {
  const [userId, setUserId] = useState(-1);

  return (
    <ThemeProvider theme={CustomizedTheme}>
      <CssBaseline />
      <Router>
        {/* If you want to navigate to a page via header's links you should added it into Header component */}
        {/* If you do not need header at all delete <Header /> */}
        {/* <Header /> */}

        {/* To add a new page to the project, you need to update the following code with the new page component. */}
        <Routes>
          <Route path="/" element={<ConsentPage setUserId={setUserId} />} />
          <Route
            path="/instruction"
            element={<InstructionPage userId={userId} />}
          />
          <Route
            path="/quiz"
            element={<QuizPage userId={userId} />}
          />
          <Route path="/game" element={<GamePage userId={userId} />} />
          <Route path="/survey" element={<SurveyPage userId={userId} />} />
          <Route path="/terminate/:status" element={<TerminatePage userId={userId} />} />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}

export default App;
