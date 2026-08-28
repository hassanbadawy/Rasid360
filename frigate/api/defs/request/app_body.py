from typing import Any, Dict, Optional

from pydantic import BaseModel


class AppConfigSetBody(BaseModel):
    requires_restart: int = 1
    update_topic: str | None = None
    # A global setting (e.g. the top-level `record:` block) is merged down into
    # every camera, and the processes that consume it subscribe per camera. One
    # topic therefore cannot describe the change; `update_topics` lets a single
    # save publish to all affected cameras instead of requiring a restart.
    update_topics: Optional[list[str]] = None
    config_data: Optional[Dict[str, Any]] = None


class AppPutPasswordBody(BaseModel):
    password: str


class AppPostUsersBody(BaseModel):
    username: str
    password: str
    role: Optional[str] = "viewer"


class AppPostLoginBody(BaseModel):
    user: str
    password: str


class AppPutRoleBody(BaseModel):
    role: str
