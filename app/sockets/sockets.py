from datetime import datetime

import socketio
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.database import get_db
from app.models.models import User

import logging
logging.basicConfig(level=logging.INFO)


# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*"
)
socket_app = socketio.ASGIApp(
    socketio_server=sio,
    socketio_path="/ws"
)

# Participants tracking
connected_users = {}

@sio.on("connect")
async def connect(sid, environ):
    logging.info(f"Client {sid} connected")

@sio.on("join")
async def join(sid, name):
    connected_users[sid] = name
    await sio.emit("update_participants", len(connected_users))
    logging.info(f"{name} joined. Total: {len(connected_users)}")

@sio.on("disconnect")
async def disconnect(sid):
    if sid in connected_users:
        del connected_users[sid]
    await sio.emit("update_participants", len(connected_users))
    logging.info(f"Client {sid} disconnected")

@sio.on("send_message")
async def handle_message(sid, data):
    await sio.emit("receive_message", data) 

@sio.on("end_chat")
async def end_chat(sid):
    await sio.emit("end_chat")
    connected_users.clear()

@sio.on("message_from_frontend")
async def message_from_frontend(sid, data):
    logging.info(f"this message is from frontend with sid : {sid}")
    logging.info(data)
    
    session = get_db()
    
    new_user = User(
        name= data['message'],
        email= f"{str(datetime.now())}@email.com",
        info= {
            "education": "asdfg",
            "work": "asdf",
            "age": 21,
            "gender": "xxx"
        }
    )
    
    try:
        session.add(new_user)
        await session.commit()  # Attempt to commit changes
        new_user_id = new_user.id

    except IntegrityError as e:
        await session.rollback()  # Rollback the transaction if an integrity error occurs
        # logging.error("Integrity error:", e)  # Log the original DB error
        return {"status": False, "error": "Integrity error"}
    except SQLAlchemyError as e:
        await session.rollback()  # Rollback for any other SQLAlchemy errors
        logging.error("Database error:", str(e))
        return {"status": False, "error": "Database error"}
    finally:
        await session.close()
    
    return {"status": True, "new_user_id": new_user_id, "message": data} 