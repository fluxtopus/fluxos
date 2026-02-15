"""Application use cases for workspace operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.domain.workspace import WorkspaceOperationsPort


@dataclass
class WorkspaceUseCases:
    """Application-layer orchestration for workspace flows."""

    workspace_ops: WorkspaceOperationsPort

    async def create_object(
        self,
        org_id: str,
        type: str,
        data: Dict[str, Any],
        created_by_type: Optional[str] = None,
        created_by_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return await self.workspace_ops.create(
            org_id=org_id,
            type=type,
            data=data,
            created_by_type=created_by_type,
            created_by_id=created_by_id,
            tags=tags,
        )

    async def get_object(self, org_id: str, object_id: str) -> Optional[Dict[str, Any]]:
        return await self.workspace_ops.get(org_id=org_id, id=object_id)

    async def update_object(
        self,
        org_id: str,
        object_id: str,
        data: Dict[str, Any],
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        return await self.workspace_ops.update(
            org_id=org_id,
            id=object_id,
            data=data,
            merge=merge,
        )

    async def delete_object(self, org_id: str, object_id: str) -> bool:
        return await self.workspace_ops.delete(org_id=org_id, id=object_id)

    async def query_objects(
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
        return await self.workspace_ops.query(
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

    async def search_objects(
        self,
        org_id: str,
        query: str,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await self.workspace_ops.search(
            org_id=org_id,
            query=query,
            type=type,
            limit=limit,
            offset=offset,
        )

    async def register_type_schema(
        self,
        org_id: str,
        type_name: str,
        schema: Dict[str, Any],
        is_strict: bool = False,
    ) -> Dict[str, Any]:
        return await self.workspace_ops.register_type(
            org_id=org_id,
            type_name=type_name,
            schema=schema,
            is_strict=is_strict,
        )

    async def list_type_schemas(self, org_id: str) -> List[Dict[str, Any]]:
        return await self.workspace_ops.list_types(org_id=org_id)

    async def get_type_schema(self, org_id: str, type_name: str) -> Optional[Dict[str, Any]]:
        return await self.workspace_ops.get_type_schema(org_id=org_id, type_name=type_name)

    async def infer_type_schema(
        self,
        org_id: str,
        type_name: str,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        return await self.workspace_ops.infer_schema(
            org_id=org_id,
            type_name=type_name,
            sample_size=sample_size,
        )
