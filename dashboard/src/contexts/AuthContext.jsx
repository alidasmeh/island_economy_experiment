import React, { createContext, useEffect, useState } from "react";

// Create the context
export const AuthContext = createContext();

// Create a provider component
export const AuthProvider = ({ children }) => {
  const [authData, setAuthData] = useState({
    email: ""
  });

  useEffect(() => {
    const emailInLocalStorage = window.localStorage.getItem("email");
    console.log("useEffect in AuthContext", emailInLocalStorage);
    // if (emailInLocalStorage) {
    //   if (emailInLocalStorage.includes("@mpib-berlin.mpg.de")) {
        setAuthData({
          email: emailInLocalStorage
        });
    //   }
    // }
  }, []);

  return (
    <AuthContext.Provider value={{ authData, setAuthData }}>
      {children}
    </AuthContext.Provider>
  );
};
