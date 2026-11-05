from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(Input):
    login_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class TicketInput(Input):
    order_id: str | None = Field(default=None, min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Write a message before sending")
        return value


class ReplyInput(Input):
    basis: Literal["ai_draft", "rejected_ai_draft", "no_ai_draft", "reply_proposal"]
    body: str = Field(min_length=1, max_length=4000)
    suggestion_id: str | None = None
    proposal_id: str | None = None
    acknowledged_warning_ids: list[str] = Field(default_factory=list)
    staff_reason_codes: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("body")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Write a reply before sending")
        return value


class SuggestionInput(Input):
    intent_override: str | None = Field(default=None, max_length=100)


class EscalationInput(Input):
    staff_reason_codes: list[str] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=2000)
    suggestion_id: str | None = None


class RoleInput(Input):
    role: Literal["staff", "manager"]


class StatusInput(Input):
    is_active: bool


class SessionView(BaseModel):
    account_id: str
    display_name: str
    role: Literal["customer", "staff", "manager", "admin"]


class SentReplyView(BaseModel):
    body: str
    sent_at: str


class ShopTicketView(BaseModel):
    ticket_id: str
    order_id: str | None
    message: str
    created_at: str
    customer_status: Literal["received", "replied"]
    reply: SentReplyView | None


class ShopTicketPage(BaseModel):
    items: list[ShopTicketView]
    next_cursor: str | None


class ProfileInput(Input):
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=40)
    address: str = Field(default='', max_length=1000)
    avatar_data_url: str | None = Field(default=None, max_length=45000)

    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        import re
        value=value.strip()
        if value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):
            raise ValueError('Enter a valid email address')
        return value

    @field_validator('phone')
    @classmethod
    def valid_phone(cls,value):
        import re
        value=value.strip()
        if value and (not re.fullmatch(r'[+0-9 .()\-]+',value) or not 6<=len(re.sub(r'\D','',value))<=15):
            raise ValueError('Enter a valid phone number')
        return value

    @field_validator('avatar_data_url')
    @classmethod
    def valid_avatar(cls,value):
        if value is None: return value
        import base64,io,re
        from PIL import Image
        if not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',value):
            raise ValueError('Choose a PNG, JPEG or WebP image')
        try:
            raw=base64.b64decode(value.split(',',1)[1],validate=True)
            if len(raw)>32768: raise ValueError()
            image=Image.open(io.BytesIO(raw))
            if image.format not in ('PNG','JPEG','WEBP') or max(image.size)>512: raise ValueError()
            image.verify()
        except Exception:
            raise ValueError('Choose a valid avatar image up to 512 pixels and 32 KB') from None
        return value

    display_name: str = Field(min_length=1, max_length=100)

    @field_validator('display_name')
    @classmethod
    def clean_name(cls,value):
        value=value.strip()
        if not value or any(ord(char)<32 for char in value):
            raise ValueError('Enter a valid display name')
        return value


class ProfileView(SessionView):
    email: str
    phone: str
    address: str
    avatar_data_url: str | None


class OrderInput(Input):
    product_id: str = Field(min_length=1, max_length=100)
