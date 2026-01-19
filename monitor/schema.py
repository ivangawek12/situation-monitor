# monitor/schema.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Event(BaseModel):
    event_id: str
    ts: datetime
    domain: str  # "geopolitics" | "cti"
    title: str
    summary: str = ""
    source_name: str
    source_url: str
    topic: Optional[str] = None
    actors: List[str] = Field(default_factory=list)
    geo: Optional[str] = None

    severity: int = 0       # 0-100
    confidence: int = 60    # 0-100
    priority: int = 0       # 0-100
    tags: List[str] = Field(default_factory=list)
