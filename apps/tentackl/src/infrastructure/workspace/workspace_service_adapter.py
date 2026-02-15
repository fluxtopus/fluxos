"""Infrastructure adapter for workspace operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.domain.workspace import WorkspaceOperationsPort
from src.interfaces.database import Database
from src.infrastructure.workspace.workspace_service import WorkspaceService


class WorkspaceServiceAdapter(WorkspaceOperationsPort):
    """Adapter exposing WorkspaceService through WorkspaceOperationsPort."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        org_id: str,
        type: str,
        data: Dict[str, Any],
        created_by_type: Optional[str] = None,
        created_by_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.create(
                org_id=org_id,
                type=type,
                data=data,
                created_by_type=created_by_type,
                created_by_id=created_by_id,
                tags=tags,
            )

    async def get(self, org_id: str, id: str) -> Optional[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.get(org_id=org_id, id=id)

    async def update(
        self,
        org_id: str,
        id: str,
        data: Dict[str, Any],
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.update(
                org_id=org_id,
                id=id,
                data=data,
                merge=merge,
            )

    async def delete(self, org_id: str, id: str) -> bool:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.delete(org_id=org_id, id=id)

    async def query(
        self,
        org_id: str,
        type: Optional[str] = None,
        where: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        created_by_id: Optional[str] = None,
        created_by_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.query(
                org_id=org_id,
                type=type,
                where=where,
                tags=tags,
                order_by=order_by,
                order_desc=order_desc,
                limit=limit,
                offset=offset,
                created_by_id=created_by_id,
                created_by_type=created_by_type,
            )

    async def search(
        self,
        org_id: str,
        query: str,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.search(
                org_id=org_id,
                query=query,
                type=type,
                limit=limit,
                offset=offset,
            )

    async def register_type(
        self,
        org_id: str,
        type_name: str,
        schema: Dict[str, Any],
        is_strict: bool = False,
    ) -> Dict[str, Any]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.register_type(
                org_id=org_id,
                type_name=type_name,
                schema=schema,
                is_strict=is_strict,
            )

    async def list_types(self, org_id: str) -> List[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.list_types(org_id=org_id)

    async def get_type_schema(self, org_id: str, type_name: str) -> Optional[Dict[str, Any]]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.get_type_schema(org_id=org_id, type_name=type_name)

    async def infer_schema(
        self,
        org_id: str,
        type_name: str,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        async with self._db.get_session() as session:
            service = WorkspaceService(session)
            return await service.infer_schema(
                org_id=org_id,
                type_name=type_name,
                sample_size=sample_size,
            )
