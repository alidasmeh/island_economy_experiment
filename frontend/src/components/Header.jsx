import React from "react";
import { AppBar, Toolbar, Typography, Button } from "@mui/material";
// import { Link } from 'react-router-dom'; // If you're using React Router for navigation
import CustomizedTheme from "../theme";
import { Link } from "react-router-dom";

function Header() {
  return (
    <AppBar
      position="static"
      sx={{
        backgroundColor: CustomizedTheme.palette.gray.main,
        color: "#383838",
      }}
    >
      <Toolbar>
        <Typography variant="h6">Project Template</Typography>
        <Button color="inherit" component={Link} to="/">
          Home
        </Button>
        {/* <Button color="inherit" component={Link} to="/call">Socket RESTfull</Button>
            <Button color="inherit" component={Link} to="/elements">Elements</Button>
            <Button color="inherit" component={Link} to="/layouts">Layouts</Button> */}
      </Toolbar>
    </AppBar>
  );
}

export default Header;
