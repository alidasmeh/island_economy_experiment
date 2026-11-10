import React from "react";
import { Container, Typography, Button } from "@mui/material";
import { useNavigate } from "react-router-dom";

function FirstPage() {
    const navigate = useNavigate();
    
    const goToPage = () => {
        navigate("/call"); // Navigate to "/call"
    };
    
    return (
        <Container maxWidth="sm">
            <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
                Project Template
            </Typography>

            <Typography variant="body1" gutterBottom>
                The purpose of developing this repo is to improve the speed of
                development of new projects.
            </Typography>

            <Typography variant="body1" gutterBottom>
                You will find exampales of most common UI elements and grid
                layouts which are developed by Material UI. You can simply find
                the element you need and copy-paste it to your project and
                customize it.
            </Typography>

            <Typography variant="body1" gutterBottom>
                In addition, this ReactJS project is coupled with a FastAPI
                backend. You will find instances of WebSocket and RESTful calls
                in this project. The code of this call can be copy-pasted, too.
                Please make sure you update the backend app as well as the
                frontend.
            </Typography>

            <hr/>
            <Typography variant="h6" gutterBottom>useNavigate instance</Typography>
            <Typography variant="body1" gutterBottom>
                Here is an example of navigating to other page with JS code, instead of "React Route DOM Link".  
            </Typography>
            <Button variant="contained" color="success" onClick={goToPage}>Go to WebSocket and RESTful calls page</Button>
        </Container>
    );
}

export default FirstPage;
