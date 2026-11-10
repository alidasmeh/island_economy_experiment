import React, { useEffect, useContext, useState } from "react";
import {
  Container,
  Typography,
  Button,
  Box,
  TextField,
  List,
  ListItem,
  ListItemText,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { SocketContext } from "../socketContext";
import { updateAccoutStatus } from "../components/updateAccountStatus";

function GamePage({ userId }) {
  const navigate = useNavigate();
   const socket = useContext(SocketContext);
  const [name, setName] = useState("");
  const [isNameSubmitted, setIsNameSubmitted] = useState(false);
  const [participants, setParticipants] = useState(0);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [chatStarted, setChatStarted] = useState(false);

  useEffect(() => {
    updateAccoutStatus(userId, "game_is_started");
  }, [userId]);

  useEffect(() => {
    socket.on("connect", () => {
      console.log("Socket connected:", socket.id);
    });

    socket.on("disconnect", (reason) => {
      console.log("Socket disconnected:", reason);
    });

    socket.on("update_participants", (count) => {
      setParticipants(count);
      if (count >= 3) {
        setChatStarted(true);
      }
    });

    socket.on("receive_message", (msg) => {
      setMessages((prev) => [...prev, msg]);
    });

    socket.on("end_chat", () => {
      navigate("/survey");
    });

    return () => {
      socket.off("connect");
      socket.off("disconnect");
      socket.off("update_participants");
      socket.off("receive_message");
      socket.off("end_chat");
};

  }, [socket, navigate]);

const handleSend = () => {
    if (message.trim()) {
      socket.emit("send_message", { name, message });
      setMessage("");
    }
  };

  const handleEndChat = () => {
    socket.emit("end_chat");
    navigate("/survey");
  };

  const handleNameSubmit = () => {
    socket.emit("join", name);
    setIsNameSubmitted(true);
  };

  return (
    <Container maxWidth="sm">
      <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
        Game Page
      </Typography>

      {!isNameSubmitted ? (
        <Box>
          <TextField
            label="Enter your name"
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <Button
            variant="contained"
            sx={{ mt: 2 }}
            onClick={handleNameSubmit}
            disabled={!name.trim()}
          >
            Submit
          </Button>
        </Box>
      ) : !chatStarted ? (
        <Typography variant="h6" sx={{ mt: 4 }}>
          Waiting for more participants... ({participants}/3)
        </Typography>
      ) : (
        <>
          <Box
            sx={{
              minHeight: 300,
              maxHeight: 300,
              overflowY: "scroll",
              background: "#f0f0f0",
              p: 2,
              borderRadius: 2,
              mt: 2,
            }}
          >
            <List>
              {messages.map((msg, idx) => (
                <ListItem key={idx}>
                  <ListItemText
                    primary={`${msg.name}: ${msg.message}`}
                  />
                </ListItem>
              ))}
            </List>
          </Box>
          <Box sx={{ display: "flex", mt: 2, gap: 1 }}>
            <TextField
              label="Type a message"
              fullWidth
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSend();
              }}
            />
            <Button variant="contained" onClick={handleSend}>
              Send
            </Button>
          </Box>
          <Button
            variant="outlined"
            color="error"
            onClick={handleEndChat}
            sx={{ mt: 2 }}
          >
            End Chat
          </Button>
        </>
      )}
    </Container>
  );
}

export default GamePage;

