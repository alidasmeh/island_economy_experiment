import os
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import socketio
import uvicorn

from app.models.database import init_db

from app.routes.routes import router  
from app.sockets.sockets import socket_app

import logging
logging.basicConfig(level=logging.INFO)

# Create FastAPI app
app = FastAPI()

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://project-template-frontend.chm.mpib-berlin.mpg.de",
        "https://project-template-dashboard.chm.mpib-berlin.mpg.de",
        "http://localhost:3000",
        "http://localhost:3001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

app.mount("/ws", socket_app)

@app.on_event("startup")
async def startup_event():
    logging.info(f"Starting FastAPI app with routes: {[route.path for route in app.routes]}")
    await init_db()