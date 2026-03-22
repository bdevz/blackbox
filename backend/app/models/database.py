import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class RFPSource(str, PyEnum):
    highergov = "highergov"
    coda = "coda"
    hubspot = "hubspot"
    manual = "manual"


class ProposalStatus(str, PyEnum):
    queued = "queued"
    generating = "generating"
    draft = "draft"
    reviewing = "reviewing"
    submitted = "submitted"
    won = "won"
    lost = "lost"
    failed = "failed"


class Outcome(str, PyEnum):
    pending = "pending"
    won = "won"
    lost = "lost"
    interview = "interview"
    no_response = "no_response"


class AgentType(str, PyEnum):
    qualify = "qualify"
    solution = "solution"
    comply = "comply"
    cost = "cost"
    review = "review"
    competitor = "competitor"
    predictor = "predictor"


class KnowledgeType(str, PyEnum):
    cert = "cert"
    rate = "rate"
    capability = "capability"
    reference = "reference"
    boilerplate = "boilerplate"
    ratecard = "ratecard"
    certification = "certification"
    slack_thread = "slack_thread"


class RFP(Base):
    __tablename__ = "rfps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(20), default="manual")
    external_id = Column(String(255), unique=True, nullable=True)
    title = Column(Text, nullable=False)
    agency_name = Column(String(500))
    agency_state = Column(String(100))
    deadline = Column(DateTime(timezone=True))
    estimated_value = Column(Numeric(15, 2))
    category = Column(String(200))
    raw_document_url = Column(Text)
    extracted_brief = Column(JSONB)
    qualification_score = Column(Float)
    ingested_at = Column(DateTime(timezone=True))
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    proposals = relationship("Proposal", back_populates="rfp")
    competitor_intel = relationship("CompetitorIntel", back_populates="rfp")


class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rfp_id = Column(UUID(as_uuid=True), ForeignKey("rfps.id"), nullable=False)
    status = Column(String(20), default="queued")
    qualification_result = Column(JSONB)
    solution_section = Column(Text)
    compliance_section = Column(Text)
    cost_section = Column(JSONB)
    review_result = Column(JSONB)
    assembled_document = Column(Text)
    prompt_versions = Column(JSONB, default=dict)
    human_review_scores = Column(JSONB, default=dict)
    outcome = Column(String(20), default="pending")
    foia_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    rfp = relationship("RFP", back_populates="proposals")
    agent_runs = relationship("AgentRun", back_populates="proposal")
    embeddings = relationship("ProposalEmbedding", back_populates="proposal")


class CompanyKnowledge(Base):
    __tablename__ = "company_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String(50), nullable=False)
    key = Column(String(500), nullable=False)
    value = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("type", "key", name="uq_knowledge_type_key"),)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False)
    agent_type = Column(String(20), nullable=False)
    model_used = Column(String(100))
    prompt_hash = Column(String(64))
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    duration_ms = Column(Integer)
    status = Column(String(10), default="ok")
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    proposal = relationship("Proposal", back_populates="agent_runs")


class ProposalEmbedding(Base):
    __tablename__ = "proposal_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey("proposals.id"), nullable=False)
    embedding = Column(Vector(1024))
    section = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    proposal = relationship("Proposal", back_populates="embeddings")


class CompetitorIntel(Base):
    __tablename__ = "competitor_intel"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rfp_id = Column(UUID(as_uuid=True), ForeignKey("rfps.id"), nullable=False)
    competitor_name = Column(String(500))
    past_contract_value = Column(Numeric(15, 2))
    incumbent_years = Column(Integer)
    data_source = Column(String(200))
    raw_data = Column(JSONB)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    rfp = relationship("RFP", back_populates="competitor_intel")


engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
