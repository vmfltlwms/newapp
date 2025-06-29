from sqlmodel import ARRAY, Column, SQLModel, Field, String
from typing import List, Optional

class Realtime_Group(SQLModel, table=True):
    group: int = Field(primary_key=True)
    strategy: int = Field(default=1)
    data_type: List[str] = Field(sa_column=Column(ARRAY(String)))
    stock_code : List[int] = Field(sa_column=Column(ARRAY(String)))
