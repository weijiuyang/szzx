from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    owner: str
    description: str
    status: str
    created_at: datetime
    project_link: str = ""
    backup_project_link: str = ""
    development_group_link: str = ""
    coordination_group_link: str = ""
    project_notes: str = ""


@dataclass(frozen=True)
class ProjectMember:
    id: int
    project_id: int
    name: str
    role: str
    dingtalk_id: str
    created_at: datetime


@dataclass(frozen=True)
class DailyReport:
    id: int
    project_id: int
    member_name: str
    role: str
    content: str
    created_at: datetime
    todo_id: int | None


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


@dataclass(frozen=True)
class ProjectTodo:
    id: int
    project_id: int
    title: str
    creator: str
    scope: str
    assignee: str
    assigned_by: str
    status: str
    completed_by: str
    created_at: datetime
    completed_at: datetime | None
    due_at: datetime | None
    started_at: datetime | None
    workflow: str = ""
    designer: str = ""
    developer: str = ""
    tester: str = ""
    acceptor: str = ""
    current_handler: str = ""
    flow_history: str = ""
    assigned_by_pet: str = "penguin"
    completed_by_pet: str = "penguin"


@dataclass(frozen=True)
class Requirement:
    id: int
    requester: str
    expected_at: date | None
    description: str
    recipient_name: str
    recipient_dingtalk_id: str
    source_conversation_id: str
    source_message_id: str
    status: str
    project_id: int | None
    todo_id: int | None
    created_at: datetime
    transfer_history: tuple[str, ...] = ()


ProjectDeck = ProjectDocument


@dataclass(frozen=True)
class WeeklyReport:
    id: int
    author: str
    content: str
    summary: str
    mood: str
    created_at: datetime


@dataclass(frozen=True)
class RestDay:
    id: int
    author: str
    day: date
    note: str
    created_at: datetime
