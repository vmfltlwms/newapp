# schemas/user_schemas.py
from typing import Optional
from sqlmodel import SQLModel


class UserBase(SQLModel):
    username: str
    email: str
    is_active: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(SQLModel):
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserRead(UserBase):
    id: int

    class Config:
        from_attributes = True