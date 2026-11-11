from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.ext.mutable import MutableDict, MutableList

from .database import Base, json_type

class User(Base):
    __tablename__ = "users_4"

    user_id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(MutableList.as_mutable(json_type()), default=list)  # change from dict to list
    surveys = Column(MutableDict.as_mutable(json_type()), default=dict)

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "participant_id": self.participant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "status": self.status,
            "surveys": self.surveys,
        }
