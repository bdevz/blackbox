from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import CompanyKnowledge, get_db

router = APIRouter()


class KnowledgeUpdate(BaseModel):
    value: dict


@router.get("/knowledge")
def list_knowledge(type: str = None, db: Session = Depends(get_db)):
    query = db.query(CompanyKnowledge)
    if type:
        query = query.filter(CompanyKnowledge.type == type)
    return query.order_by(CompanyKnowledge.updated_at.desc()).all()


@router.patch("/knowledge/{knowledge_id}")
def update_knowledge(knowledge_id: UUID, update: KnowledgeUpdate, db: Session = Depends(get_db)):
    item = db.query(CompanyKnowledge).filter(CompanyKnowledge.id == knowledge_id).first()
    if not item:
        raise HTTPException(404, "Knowledge item not found")
    item.value = update.value
    db.commit()
    return {"status": "updated"}
