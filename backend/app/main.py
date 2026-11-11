import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.database import init_db

from app.routes.routes import router
from app.routes.game_routes import game_router
from app.sockets.sockets import socket_app, transport
from app.game.service import init_service

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
    ] + [o for o in os.getenv("EXTRA_CORS_ORIGINS", "").split(",") if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(game_router)

app.mount("/ws", socket_app)


@app.on_event("startup")
async def startup_event():
    logging.info(f"Starting FastAPI app with routes: {[route.path for route in app.routes]}")
    await init_db()
    svc = init_service(transport)
    logging.info(f"Island Economy params {svc.cfg.source_path} sha256={svc.cfg.sha256[:12]} code={svc.code_version}")


@app.on_event("shutdown")
async def shutdown_event():
    from app.game.service import get_service
    await get_service().lobby.shutdown()
