import React, { useState, useContext } from "react";
import { useNavigate } from "react-router";

import {
  Button,
  TextField,
  Box,
  Typography,
  Container,
  CssBaseline,
  Paper,
} from "@mui/material";

import { AuthContext } from "../contexts/AuthContext";
import { login } from "../api";

export default function LoginPage() {
  const navigator = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");

  const { setAuthData } = useContext(AuthContext);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    try {
      const { username } = await login(email, password);
      setAuthData({ email: username });
      navigator("/");
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <Container component="main" maxWidth="xs">
      <CssBaseline />
      <Paper elevation={6} sx={{ p: 4, mt: 8, borderRadius: 3 }}>
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
          }}
        >
          <Box sx={{ m: 1 }}>
            <img
              src="./logo512.png"
              alt="Logo"
              style={{ width: 60, height: 60, borderRadius: "50%" }}
            />
          </Box>
          <Typography align="center" component="h1" variant="h5">
            Island Economy<br /> Researcher Dashboard
          </Typography>
          <Box component="form" onSubmit={handleSubmit} sx={{ mt: 1 }}>
            <TextField
              margin="normal"
              required
              fullWidth
              label="Username"
              type="text"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              margin="normal"
              required
              fullWidth
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {error && <Typography color="error">{error}</Typography>}

            <Button
              type="submit"
              fullWidth
              variant="contained"
              sx={{ mt: 3, mb: 2 }}
            >
              Sign In
            </Button>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
}
