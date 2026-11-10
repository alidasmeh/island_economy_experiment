export const updateAccoutStatus = async (userId, status) => {
  console.log("updateAccoutStatus is called ", {
    userId,
    status
  })
  let baseUrl = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
  const response = await fetch(`${baseUrl}/update_user_status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      status: status,
    }),
  });
  const data = await response.json();
  console.log("updateAccout > ", data);
  if (data.status) {
    return true;
  } else {
    console.log(response);
  }

  alert("there is a problem in updateAccoutStatus")
  return false;
};