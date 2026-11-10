import React, { useState } from "react";
import {
    Typography,
    Button,
    ButtonGroup,
    List,
    ListItem,
    Box,
} from "@mui/material";

import ContainersComponent from "../components/LayoutsPage/Components";
import GridsComponent from "../components/LayoutsPage/Girds";

function LayoutsPage() {
    const [componentToShow, setComponentToShow] = useState("");

    const showComponent = (componentName) => {
        setComponentToShow(componentName);
    };

    return (
        <>
            <Typography variant="h4" gutterBottom sx={{ mt: 5 }}>
                Layouts
            </Typography>

            <Typography variant="body1" gutterBottom>
                In this page you will find two things:
            </Typography>
            <List component="ol">
                <ListItem component="li">- Different Layouts</ListItem>
                <ListItem component="li">
                    - How to navigate in between components, it makes an
                    experience like changing page, but without changing URL.
                </ListItem>
            </List>

            <Box sx={{ textAlign: "center", mb: 4 }} >
                <ButtonGroup variant="outlined" aria-label="Basic button group">
                    <Button onClick={() => showComponent("containers")}>
                        Containers
                    </Button>
                    <Button onClick={() => showComponent("grid")}>grid</Button>
                </ButtonGroup>
            </Box>

            <Box component="section">
                {componentToShow === "containers" && <ContainersComponent />}
                {componentToShow === "grid" && <GridsComponent />}
            </Box>
        </>
    );
}

export default LayoutsPage;
