from typing import TypeVar, Generic, Type, List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from dataclasses import dataclass

T = TypeVar('T')


@dataclass
class Page:
    items: List[Any]
    total: int
    page: int
    size: int

    @property
    def pages(self) -> int:
        return (self.total + self.size - 1) // self.size if self.size > 0 else 0


class BaseRepository(Generic[T]):
    def __init__(self, session: Session, model: Type[T]):
        self.session = session
        self.model = model

    def find(self, pk) -> Optional[T]:
        return self.session.get(self.model, pk)

    def find_all(self) -> List[T]:
        return self.session.query(self.model).all()

    def find_by(self, **filters) -> Optional[T]:
        return self.session.query(self.model).filter_by(**filters).first()

    def find_all_by(self, **filters) -> List[T]:
        return self.session.query(self.model).filter_by(**filters).all()

    def search(self, term: str, fields: List[str]) -> List[T]:
        conditions = [getattr(self.model, f).ilike(f"%{term}%") for f in fields]
        return self.session.query(self.model).filter(or_(*conditions)).all()

    def find_paginated(self, page: int = 0, size: int = 10, **filters) -> Page:
        query = self.session.query(self.model).filter_by(**filters)
        total = query.count()
        items = query.offset(page * size).limit(size).all()
        return Page(items=items, total=total, page=page, size=size)

    def save(self, entity: T) -> T:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def update(self, entity: T) -> T:
        merged = self.session.merge(entity)
        self.session.commit()
        return merged

    def delete(self, pk) -> None:
        entity = self.find(pk)
        if entity:
            self.session.delete(entity)
            self.session.commit()


class BaseService(Generic[T]):
    def __init__(self, repo: BaseRepository[T]):
        self.repo = repo

    def get(self, pk) -> Optional[T]:
        return self.repo.find(pk)

    def list(self, **filters) -> List[T]:
        return self.repo.find_all_by(**filters) if filters else self.repo.find_all()

    def search(self, term: str, fields: List[str]) -> List[T]:
        return self.repo.search(term, fields)

    def paginate(self, page: int = 0, size: int = 10, **filters) -> Page:
        return self.repo.find_paginated(page=page, size=size, **filters)

    def create(self, entity: T) -> T:
        return self.repo.save(entity)

    def update(self, entity: T) -> T:
        return self.repo.update(entity)

    def delete(self, pk) -> None:
        self.repo.delete(pk)
