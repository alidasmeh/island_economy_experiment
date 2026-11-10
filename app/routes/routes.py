# routes.py
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy import select, desc, or_, and_, asc, delete
from pydantic import BaseModel

from app.models.database import get_db
from app.models.models import User

from .dashboard import dashboard_router

import logging

logging.basicConfig(level=logging.INFO)

router = APIRouter()
router.include_router(dashboard_router)

@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/create_a_user/{participant_id}")
async def create_a_user_endpoint(participant_id: str):
    async with get_db() as db:
        result = await db.execute(
            select(User).where(User.participant_id == participant_id)
        )
        user = result.scalars().all()

        if len(user) > 0:
            return {"status": False, "error": "This participant_id is already started."}

        new_user = User(
            participant_id=participant_id,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        logging.info(f"new user id : {new_user.user_id}")

        return {"status": True, "user_id": new_user.user_id}


class UpdateUserStatusPayload(BaseModel):
    user_id: int
    status: str


@router.post("/update_user_status")
async def update_user_status_endpoint(payload: UpdateUserStatusPayload):
    async with get_db() as db:
        results = await db.execute(
            select(User).where(User.user_id == int(payload.user_id))
        )
        user = results.scalar_one_or_none()

        if user:
            if user.status is None:
                user.status = []

            user.status.append(
                {"status": payload.status, "updated_at": datetime.utcnow().isoformat()}
            )

            db.add(user)
            await db.commit()
            await db.refresh(user)
            return {
                "status": True,
                "user": user.to_dict(),
            }
        else:
            return {"status": False, "message": "User not found"}


class SurveyUpdatePayload(BaseModel):
    user_id: int
    survey: Any
    survey_title: str


@router.post("/survey_update")
async def survey_update_endpoint(payload: SurveyUpdatePayload):
    async with get_db() as db:
        results = await db.execute(
            select(User).where(User.user_id == int(payload.user_id))
        )
        user = results.scalar_one_or_none()

        if user:

            user.surveys[payload.survey_title] = payload.survey

            db.add(user)
            await db.commit()
            await db.refresh(user)
            return {
                "status": True,
                "user": user.to_dict(),
            }
