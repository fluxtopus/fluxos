"""Domain ports for workspace operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class WorkspaceOperationsPort(Protocol):
    """Port for workspace CRUD/query/schema operations."""

    async def create(
        self,
        org_id: str,
        type: str,
        data: Dict[str, Any],
        created_by_type: Optional[str] = None,
        created_by_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        ...

    async def get(self, org_id: str, id: str) -> Optional[Dict[str, Any]]:
        ...

    async def update(
        self,
        org_id: str,
        id: str,
        data: Dict[str, Any],
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        ...

    async def delete(self, org_id: str, id: str) -> bool:
        ...

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
        ...

    async def search(
        self,
        org_id: str,
        query: str,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        ...

    async def register_type(
        self,
        org_id: str,
        type_name: str,
        schema: Dict[str, Any],
        is_strict: bool = False,
    ) -> Dict[str, Any]:
        ...

    async def list_types(self, org_id: str) -> List[Dict[str, Any]]:
        ...

    async def get_type_schema(self, org_id: str, type_name: str) -> Optional[Dict[str, Any]]:
        ...

    async def infer_schema(
        self,
        org_id: str,
        type_name: str,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        ...
