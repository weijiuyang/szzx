from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    owner: str
    description: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectMember:
    id: int
    project_id: int
    name: str
    role: str
    created_at: datetime


@dataclass(frozen=True)
class DailyReport:
    id: int
    project_id: int
    member_name: str
    role: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectWeeklyReport:
    id: int
    project_id: int
    author: str
    content: str
    created_at: datetime


@dataclass(frozen=True)
class ProjectDocument:
    id: int
    project_id: int
    title: str
    doc_type: str
    visibility: str
    uploader: str
    file_path: str
    created_at: datetime


ProjectDeck = ProjectDocument


@dataclass(frozen=True)
class WeeklyReport:
    id: int
    content: str
    summary: str
    mood: str
    created_at: datetime
