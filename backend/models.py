from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base
from backend.utils.encryption import encrypt_value, decrypt_value, ENCRYPTION_KEY

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    integrations = relationship("Integration", back_populates="organization")
    knowledge_chunks = relationship("KnowledgeChunk", back_populates="organization")
    audit_logs = relationship("AuditLog", back_populates="organization")

class Integration(Base):
    __tablename__ = "integrations"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"))
    platform = Column(String)  # 'gorgias' or 'bigcommerce'
    api_key_encrypted = Column(String)
    
    # Store additional connection info like base_url or store_hash in JSON
    # Or keep separate columns if schema is rigid. Given 'platform-agnostic', 
    # we might need a generic config, but explicit columns help queryability.
    credentials = Column(JSON, default={}) 
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="integrations")

    @property
    def api_key(self):
        return decrypt_value(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value):
        self.api_key_encrypted = encrypt_value(value)

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"))
    pinecone_id = Column(String, unique=True, index=True)
    content_hash = Column(String) # For duplicate checks
    source_type = Column(String)  # e.g., 'ticket', 'order', 'product'
    source_id = Column(String) # External ID
    metadata_json = Column(JSON, default={}) # Flexible metadata storage
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="knowledge_chunks")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"))
    action = Column(String) # e.g., 'ingest', 'query', 'update_config'
    details = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="audit_logs")
