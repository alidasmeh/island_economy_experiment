import React, { createContext, useState } from "react";
import { forgetLogin, storedLogin } from "../api";

export const AuthContext = createContext();

// The researcher is logged in while this tab holds credentials accepted by the game server.
export const AuthProvider = ({ children }) => {
  const [authData, setAuthData] = useState(() => {
    const s = storedLogin();
    return { email: s ? s.username : "" };
  });

  const logout = () => {
    forgetLogin();
    setAuthData({ email: "" });
  };

  return <AuthContext.Provider value={{ authData, setAuthData, logout }}>{children}</AuthContext.Provider>;
};
