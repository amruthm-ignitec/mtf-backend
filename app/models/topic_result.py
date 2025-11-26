from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database.database import Base

class TopicResult(Base):
    __tablename__ = "topic_results"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    topic_name = Column(String, nullable=False, index=True)  # e.g., "Cancer History", "Diabetes"
    summary = Column(Text, nullable=True)  # Summary text for this topic
    citations = Column(JSON, nullable=True)  # List of citations with page numbers
    source_pages = Column(JSON, nullable=True)  # List of page numbers where topic was found
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", backref="topic_results")

