import React, { useEffect, useState } from 'react';
import { 
  Button, 
  TextField, 
  Container, 
  Stack, 
  Typography 
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';

import {socket} from '../socket'


function SocketRestPage() {

  const [messageText, setMessageText] = useState("")

  const sendMessageBySocket = async () => {
    if (socket.connected) {
      console.log("message is sent")
      socket.emit("message_from_frontend", {
        message: messageText
      }, (ack) => {
        console.log("Acknowledgment received from backend:", ack);
      });
      setMessageText("")
    } else {
      console.log("Socket not connected yet, cannot send message.");
      // Optionally, you could queue the message or inform the user
    }
  }

  const sendMessageByRest = async () => {
    const LocalBackendUrl = "http://localhost:8000"
    let baseUrl = process.env.REACT_APP_BACKEND_URL || LocalBackendUrl;

    if (baseUrl !== LocalBackendUrl && baseUrl.startsWith("http://")) {
      baseUrl = baseUrl.replace("http://", "https://");
    }

    console.log("baseUrl" , baseUrl)

    const response = await fetch(`${baseUrl}/send_message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: "test",
        email: "test@test.de"
      }),
    });

    if (!response.ok) {
      const errorMessage = await response.text(); // Or response.json() for structured errors
      throw new Error(`HTTP error! status: ${response.status}, message: ${errorMessage}`);
    }
    const responseData = await response.json()
    console.log("restful call response", responseData)
    setMessageText("")
  }

  useEffect(()=>{
    socket.connect();

    socket.on('connect', ()=>{
      console.log("socket connect is called")
    })
    
    return () => {
      socket.off('connect');
    };
  }, [])

  return (
    <Container maxWidth="sm">
      <Typography variant="h4" gutterBottom sx={{mt:5}}>
        Welcome to MUI
      </Typography>
      <Stack spacing={2}>
        <TextField
          fullWidth
          label="Enter your name"
          variant="outlined"
          value={messageText}
          onChange={(e)=> setMessageText(e.target.value)}
        />
        <Button
          fullWidth
          variant="contained"
          color="primary"
          endIcon={<SendIcon />}
          onClick={sendMessageBySocket}
        >
          Send by Socket
        </Button>
        <Button
          fullWidth
          variant="contained"
          color="secondary"
          endIcon={<SendIcon />}
          onClick={sendMessageByRest}
        >
          Send by RESTful
        </Button>
      </Stack>
    </Container>
  );
}

export default SocketRestPage;