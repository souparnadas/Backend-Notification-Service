from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from models import ChannelType, PriorityLevel, NotificationStatus
from typing import List
class NotificationRequest(BaseModel):
    user_id: str
    channel: ChannelType
    priority: PriorityLevel = PriorityLevel.NORMAL
    template_name: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None

class NotificationResponse(BaseModel):
    id: str
    status: NotificationStatus
    message: str

class PreferenceUpdate(BaseModel):
    channel: ChannelType
    is_enabled: bool
class UserPreferencesPayload(BaseModel):
    preferences: Dict[str, bool]

class UserPreferenceResponse(BaseModel):
    user_id: str
    preferences: Dict[str, bool]

class BatchNotificationRequest(BaseModel):
    user_ids: List[str]
    channel: ChannelType
    priority: PriorityLevel = PriorityLevel.NORMAL
    template_name: str
    variables: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        schema_extra = {
            "example": {
                "user_ids": ["user_1", "user_2", "user_3"],
                "channel": "EMAIL",
                "template_name": "welcome",
                "variables": {"discount": "20%"}
            }
        }

class WebhookCreate(BaseModel):
    url: str