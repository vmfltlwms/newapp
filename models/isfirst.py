from datetime import date
from sqlmodel import SQLModel, Field
from typing import Optional

class IsFirst(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    check_date: date = Field(default_factory=date.today)  # sa_column 생략 가능
    is_first: bool = Field(default=True)