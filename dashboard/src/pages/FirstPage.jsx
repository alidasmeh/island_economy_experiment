import React, { useEffect, useState } from "react";
import {
  Container,
  Typography,
  List,
  ListItem,
  ListItemText,
  Divider,
} from "@mui/material";
import { useNavigate } from "react-router-dom";

import PageTracker from "../components/PageTracker";

function FirstPage() {
  const navigate = useNavigate();

  const [users, setUsers] = useState([])

  const goToPage = (userId) => {
    if (userId === -1) return;
    navigate(`/project/${userId}`);
  };

  const fetchUsers = async () => {
    let baseUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";

    const response = await fetch(`${baseUrl}/dashboard/get_list_of_users`);
    const data = await response.json();

    if (data.status) {
      setUsers(data.list.reverse())
      console.log(data)
    } else {
      alert(data.error);
      console.log(response);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return (
    <>
      <PageTracker arr={[]} />
      <Container maxWidth="md">
        <Typography
          variant="h4"
          gutterBottom
          sx={{ mt: 0, textAlign: "center" }}
        >
          List of Users
        </Typography>
        <div>
          <List
            sx={{
              p: 0,
              width: "100%",
              borderRadius: 2,
              border: "1px solid",
              borderColor: "divider",
              backgroundColor: "background.paper",
            }}
            aria-label="mailbox folders"
          >
            {users.map((user, index) => {
              return (
                <div key={index}>
                  <ListItem
                    sx={{
                      transition: "all 0.2s",
                      cursor: "pointer",
                      "&:hover": {
                        backgroundColor: "#eee",
                      },
                    }}
                    onClick={() => goToPage(user.user_id)}
                  >
                    <ListItemText
                      primary={
                        "userId " +
                        user.user_id+
                        " - participant_id : " +
                        user.participant_id
                      }
                    />
                  </ListItem>
                  <Divider component="li" />
                </div>
              );
            })}
          </List>
        </div>
      </Container>
    </>
  );
}

export default FirstPage;
