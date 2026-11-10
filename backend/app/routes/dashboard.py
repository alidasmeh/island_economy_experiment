import os

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select, desc, or_, and_, asc, delete

from app.models.models import User
from app.models.database import get_db

import logging

logging.basicConfig(level=logging.INFO)

# Create an APIRouter for authentication endpoints
dashboard_router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")


@dashboard_router.get("/login/{username}/{password}")
async def get_user(username: str, password: str):
    if username == DASHBOARD_USERNAME and password == DASHBOARD_PASSWORD:
        return {"status": True}
    else:
        logging.info("Checking error:")
        logging.info(username == DASHBOARD_USERNAME)
        logging.info(username)
        logging.info(DASHBOARD_USERNAME)
        raise HTTPException(status_code=404, detail="User not found")


@dashboard_router.get("/get_list_of_users")
async def get_list_of_users():
    async with get_db() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        if users:
            list_of_users = []

            for user in users:
                list_of_users.append(user.to_dict())

            return {"status": True, "list": list_of_users}

        return {"status": False, "list": list_of_users}


@dashboard_router.get("/get_user/{user_id}")
async def get_user(user_id: str):
    async with get_db() as db:
        result = await db.execute(select(User).where(User.user_id == int(user_id)))
        user = result.scalar_one_or_none()

        if user:

            return {"status": True, "data": user.to_dict()}

        return {"status": False, "error": "user_id not found"}
