from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from repository.database import Base
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

# --- Job Queue Model ---
class JobQueue(Base):
    __tablename__ = 'job_queue'

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(255), nullable=False)

    task_name = Column(String(100), nullable=False)  # Task type
    status = Column(String(50), default='pending')  # pending, in-progress, completed, failed

    issued_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    issued_by = Column(Integer, nullable=True)  # User ID who issued the task


    def __init__(self, device_id, task_name, status="pending"):
        self.device_id = device_id
        self.task_name = task_name
        self.status = status

    def __repr__(self):
        return f"<JobQueue(id={self.id}, device_id={self.device_id}, task={self.task_name}, status={self.status})>"
