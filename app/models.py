from sqlalchemy import Column, Integer, String, JSON, UUID
from app.database import Base
import uuid
from sqlalchemy.dialects.postgresql import UUID


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    repo = Column(String, index=True)
    pr_number = Column(Integer)
    status = Column(String, default="PENDING")
    result = Column(JSON, nullable=True)
