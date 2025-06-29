
from datetime import date
from sqlmodel import SQLModel, Field, Session, select
from typing import Optional

class IsFirst(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    check_date: date = Field(default_factory=date.today)
    is_first: bool = Field(default=True)

def check_and_update_first(session: Session) -> int:
    """
    오늘 날짜를 확인하여 첫 번째 접근인지 체크하고 상태를 업데이트합니다.
    
    Args:
        session: SQLModel Session 객체
        
    Returns:
        int: 첫 번째 접근이면 1, 아니면 0
    """
    today = date.today()
    
    # 오늘 날짜의 레코드 조회
    statement = select(IsFirst).where(IsFirst.check_date == today)
    existing_record = session.exec(statement).first()
    
    if existing_record is None:
        # 오늘 첫 번째 접근 - 새 레코드 생성
        new_record = IsFirst(check_date=today, is_first=False)
        session.add(new_record)
        session.commit()
        return 1
    else:
        # 이미 오늘 접근한 적이 있음
        if existing_record.is_first:
            # 아직 첫 번째 상태였다면 False로 변경
            existing_record.is_first = False
            session.commit()
            return 1
        else:
            # 이미 첫 번째가 아닌 상태
            return 0