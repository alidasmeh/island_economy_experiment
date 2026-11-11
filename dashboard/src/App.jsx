import React, { useContext, useEffect, useState } from "react";
import { ThemeProvider } from "@mui/material/styles";
import CssBaseline from "@mui/material/CssBaseline";
import CustomizedTheme from "./theme";
import Sidebar from "./components/Sidebar";
import {
  BrowserRouter as Router,
  Route,
  Navigate,
  Routes
} from "react-router-dom";

import { AuthContext } from "./contexts/AuthContext";

import LoginPage from "./pages/LoginPage";

import SessionsPage from "./pages/SessionsPage";
import SessionDetailPage from "./pages/SessionDetailPage";

function App() {
  const { authData } = useContext(AuthContext);

  function DelayedRedirect({ to, delay = 100 }) {
    const [shouldRedirect, setShouldRedirect] = useState(false);

    useEffect(() => {
      const timer = setTimeout(() => {
        setShouldRedirect(true);
      }, delay);

      return () => clearTimeout(timer);
    }, [delay]);

    return shouldRedirect ? <Navigate to={to} replace /> : null;
  }

  return (
    <ThemeProvider theme={CustomizedTheme}>
      <CssBaseline />
      <Router>
        {authData.email && <Sidebar />}
        <Routes>
          <Route
            path="/login"
            element={
              !authData?.email ? <LoginPage /> : <Navigate to="/" replace />
            }
          />
          <Route
            path="/"
            element={
              authData?.email ? (
                <SessionsPage />
              ) : (
                <DelayedRedirect to="/login" replace />
              )
            }
          />
          <Route
            path="/sessions/:code"
            element={
              authData?.email ? (
                <SessionDetailPage />
              ) : (
                <DelayedRedirect to="/login" replace />
              )
            }
          />
        </Routes>
      </Router>
    </ThemeProvider>
  );
}

export default App;
