# REVIEW: Service exposes Mongo-style query operators directly; needs guardrails
# REVIEW: for expensive queries.
# REVIEW: Validation produces warnings but does not prevent writes; data quality
# REVIEW: enforcement is weak.
"""
Workspace Service

Provides CRUD operations and queries for flexible workspace objects.
Supports any data type (events, contacts, custom) without schema migrations.

Features:
- MongoDB-style query operators
- Full-text search via PostgreSQL tsvector
- Optional JSON Schema validation
- Type normalization to prevent duplicates
- Link validation for references
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import re
import uuid
import structlog

from sqlalchemy import select, update, delete, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.database.workspace_models import WorkspaceObject, WorkspaceTypeSchema

logger = structlog.get_logger(__name__)


class WorkspaceService:
    """
    Service for flexible object storage operations.

    All methods require org_id for multi-tenant isolation.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize workspace service.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    # ===========================================
    # CRUD Operations
    # ===========================================

    async def create(
        self,
        org_id: str,
        type: str,
        data: Dict[str, Any],
        created_by_type: Optional[str] = None,
        created_by_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new workspace object.

        Args:
            org_id: Organization ID for isolation
            type: Object type (e.g., "event", "contact")
            data: Object data as dict
            created_by_type: Creator type ("user" or "agent")
            created_by_id: Creator ID
            tags: Optional tags for filtering

        Returns:
            Created object as dict with warnings if any
        """
        # Normalize type name
        normalized_type = self._normalize_type(type)

        # Validate data against schema if registered
        warnings = await self._validate_data(org_id, normalized_type, data)

        # Validate links (fields ending in _id)
        link_warnings = await self._validate_links(org_id, data)
        warnings.extend(link_warnings)

        # Create object
        obj = WorkspaceObject(
            id=uuid.uuid4(),
            org_id=org_id,
            type=normalized_type,
            data=data,
            tags=tags or [],
            created_by_type=created_by_type,
            created_by_id=created_by_id,
        )

        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)

        result = self._to_dict(obj)
        if warnings:
            result["warnings"] = warnings

        logger.info(
            "Workspace object created",
            org_id=org_id,
            type=normalized_type,
            object_id=str(obj.id),
        )

        return result

    async def get(self, org_id: str, id: str) -> Optional[Dict[str, Any]]:
        """
        Get a workspace object by ID.

        Args:
            org_id: Organization ID for isolation
            id: Object UUID

        Returns:
            Object as dict or None if not found
        """
        try:
            obj_id = uuid.UUID(id)
        except ValueError:
            return None

        result = await self.session.execute(
            select(WorkspaceObject).where(
                and_(
                    WorkspaceObject.id == obj_id,
                    WorkspaceObject.org_id == org_id,
                )
            )
        )
        obj = result.scalar_one_or_none()

        return self._to_dict(obj) if obj else None

    async def update(
        self,
        org_id: str,
        id: str,
        data: Dict[str, Any],
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Update a workspace object.

        Args:
            org_id: Organization ID for isolation
            id: Object UUID
            data: New data (merged or replaced based on merge flag)
            merge: If True, merge with existing data. If False, replace.

        Returns:
            Updated object as dict or None if not found
        """
        try:
            obj_id = uuid.UUID(id)
        except ValueError:
            return None

        # Get existing object
        result = await self.session.execute(
            select(WorkspaceObject).where(
                and_(
                    WorkspaceObject.id == obj_id,
                    WorkspaceObject.org_id == org_id,
                )
            )
        )
        obj = result.scalar_one_or_none()

        if not obj:
            return None

        # Merge or replace data
        if merge:
            new_data = {**obj.data, **data}
        else:
            new_data = data

        # Validate data
        warnings = await self._validate_data(org_id, obj.type, new_data)
        link_warnings = await self._validate_links(org_id, new_data)
        warnings.extend(link_warnings)

        # Update
        obj.data = new_data
        obj.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(obj)

        result = self._to_dict(obj)
        if warnings:
            result["warnings"] = warnings

        logger.info(
            "Workspace object updated",
            org_id=org_id,
            object_id=id,
            merge=merge,
        )

        return result

    async def delete(self, org_id: str, id: str) -> bool:
        """
        Delete a workspace object.

        Args:
            org_id: Organization ID for isolation
            id: Object UUID

        Returns:
            True if deleted, False if not found
        """
        try:
            obj_id = uuid.UUID(id)
        except ValueError:
            return False

        result = await self.session.execute(
            delete(WorkspaceObject).where(
                and_(
                    WorkspaceObject.id == obj_id,
                    WorkspaceObject.org_id == org_id,
                )
            )
        )

        await self.session.commit()
        deleted = result.rowcount > 0

        if deleted:
            logger.info(
                "Workspace object deleted",
                org_id=org_id,
                object_id=id,
            )

        return deleted

    # ===========================================
    # Query Operations
    # ===========================================

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
        """
        Query workspace objects with filters.

        Args:
            org_id: Organization ID for isolation
            type: Filter by type
            where: MongoDB-style query operators
            tags: Filter by tags (all must match)
            order_by: Field to order by (supports data.field)
            order_desc: If True, order descending
            limit: Max results (default 100)
            offset: Skip first N results

        Returns:
            List of matching objects as dicts
        """
        # Start with org isolation
        conditions = [WorkspaceObject.org_id == org_id]

        # Filter by type
        if type:
            conditions.append(WorkspaceObject.type == self._normalize_type(type))

        # Filter by tags (all must match)
        if tags:
            for tag in tags:
                conditions.append(WorkspaceObject.tags.contains([tag]))

        # Filter by creator identity (uses idx_workspace_created_by index)
        if created_by_id:
            conditions.append(WorkspaceObject.created_by_id == created_by_id)
        if created_by_type:
            conditions.append(WorkspaceObject.created_by_type == created_by_type)

        # Translate where clause
        if where:
            where_conditions = self._translate_where(where)
            conditions.extend(where_conditions)

        # Build query
        query = select(WorkspaceObject).where(and_(*conditions))

        # Ordering
        if order_by:
            if order_by.startswith("data."):
                field_path = order_by[5:]
                order_col = WorkspaceObject.data[field_path].astext
            elif order_by == "created_at":
                order_col = WorkspaceObject.created_at
            elif order_by == "updated_at":
                order_col = WorkspaceObject.updated_at
            else:
                order_col = WorkspaceObject.created_at

            if order_desc:
                query = query.order_by(order_col.desc())
            else:
                query = query.order_by(order_col)
        else:
            query = query.order_by(WorkspaceObject.created_at.desc())

        # Pagination
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        objects = result.scalars().all()

        return [self._to_dict(obj) for obj in objects]

    async def search(
        self,
        org_id: str,
        query: str,
        type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across workspace objects.

        Args:
            org_id: Organization ID for isolation
            query: Search query string
            type: Optional type filter
            limit: Max results
            offset: Skip first N results

        Returns:
            List of matching objects as dicts
        """
        conditions = [WorkspaceObject.org_id == org_id]

        if type:
            conditions.append(WorkspaceObject.type == self._normalize_type(type))

        # Full-text search using search_vector
        conditions.append(
            WorkspaceObject.search_vector.op("@@")(
                func.plainto_tsquery("english", query)
            )
        )

        stmt = (
            select(WorkspaceObject)
            .where(and_(*conditions))
            .order_by(
                func.ts_rank(
                    WorkspaceObject.search_vector,
                    func.plainto_tsquery("english", query),
                ).desc()
            )
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        objects = result.scalars().all()

        return [self._to_dict(obj) for obj in objects]

    # ===========================================
    # Type Schema Management
    # ===========================================

    async def register_type(
        self,
        org_id: str,
        type_name: str,
        schema: Dict[str, Any],
        is_strict: bool = False,
    ) -> Dict[str, Any]:
        """
        Register a JSON Schema for a type.

        Args:
            org_id: Organization ID
            type_name: Type to register schema for
            schema: JSON Schema definition
            is_strict: If True, reject invalid data. If False, warn only.

        Returns:
            Registered schema as dict
        """
        normalized_type = self._normalize_type(type_name)

        # Upsert schema
        stmt = insert(WorkspaceTypeSchema).values(
            id=uuid.uuid4(),
            org_id=org_id,
            type_name=normalized_type,
            schema=schema,
            is_strict=is_strict,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_workspace_type_schema",
            set_={
                "schema": schema,
                "is_strict": is_strict,
                "updated_at": datetime.utcnow(),
            },
        )

        await self.session.execute(stmt)
        await self.session.commit()

        logger.info(
            "Type schema registered",
            org_id=org_id,
            type_name=normalized_type,
            is_strict=is_strict,
        )

        return {
            "type_name": normalized_type,
            "schema": schema,
            "is_strict": is_strict,
        }

    async def get_type_schema(
        self,
        org_id: str,
        type_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get registered schema for a type.

        Args:
            org_id: Organization ID
            type_name: Type name

        Returns:
            Schema definition or None if not registered
        """
        normalized_type = self._normalize_type(type_name)

        result = await self.session.execute(
            select(WorkspaceTypeSchema).where(
                and_(
                    WorkspaceTypeSchema.org_id == org_id,
                    WorkspaceTypeSchema.type_name == normalized_type,
                )
            )
        )
        schema_obj = result.scalar_one_or_none()

        if schema_obj:
            return {
                "type_name": schema_obj.type_name,
                "schema": schema_obj.schema,
                "is_strict": schema_obj.is_strict,
            }
        return None

    async def list_types(self, org_id: str) -> List[Dict[str, Any]]:
        """
        List all registered types for an organization.

        Returns:
            List of type schemas
        """
        result = await self.session.execute(
            select(WorkspaceTypeSchema).where(
                WorkspaceTypeSchema.org_id == org_id
            )
        )
        schemas = result.scalars().all()

        return [
            {
                "type_name": s.type_name,
                "schema": s.schema,
                "is_strict": s.is_strict,
            }
            for s in schemas
        ]

    async def infer_schema(
        self,
        org_id: str,
        type_name: str,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Infer schema from existing objects of a type.

        Analyzes data fields to determine common structure.

        Args:
            org_id: Organization ID
            type_name: Type to analyze
            sample_size: Max objects to analyze

        Returns:
            Inferred schema with field statistics
        """
        objects = await self.query(
            org_id=org_id,
            type=type_name,
            limit=sample_size,
        )

        if not objects:
            return {
                "type": type_name,
                "sample_size": 0,
                "fields": {},
            }

        # Analyze fields
        field_stats: Dict[str, Dict[str, Any]] = {}
        total = len(objects)

        for obj in objects:
            data = obj.get("data", {})
            for key, value in data.items():
                if key not in field_stats:
                    field_stats[key] = {"count": 0, "types": set()}
                field_stats[key]["count"] += 1
                field_stats[key]["types"].add(type(value).__name__)

        return {
            "type": type_name,
            "sample_size": total,
            "fields": {
                k: {
                    "frequency": f"{v['count']/total*100:.1f}%",
                    "types": list(v["types"]),
                }
                for k, v in field_stats.items()
            },
        }

    # ===========================================
    # Mitigation Methods
    # ===========================================

    def _normalize_type(self, type_name: str) -> str:
        """
        Normalize type names to prevent duplicates.

        - Lowercase
        - Strip whitespace
        - Replace spaces with underscores
        - Remove special characters
        """
        normalized = type_name.lower().strip().replace(" ", "_")
        normalized = re.sub(r"[^a-z0-9_]", "", normalized)
        return normalized

    async def _validate_data(
        self,
        org_id: str,
        type_name: str,
        data: Dict[str, Any],
    ) -> List[str]:
        """
        Validate data against registered schema.

        Returns warnings or raises ValidationError if strict.
        """
        schema_def = await self.get_type_schema(org_id, type_name)
        if not schema_def:
            return []  # No schema = no validation

        try:
            import jsonschema
            jsonschema.validate(data, schema_def["schema"])
            return []
        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            if schema_def["is_strict"]:
                raise ValueError(error_msg)
            return [error_msg]
        except ImportError:
            # jsonschema not installed, skip validation
            return []

    async def _validate_links(
        self,
        org_id: str,
        data: Dict[str, Any],
    ) -> List[str]:
        """
        Validate fields ending in _id reference existing objects.

        Returns warnings for broken references.
        """
        warnings = []
        for key, value in data.items():
            if key.endswith("_id") and isinstance(value, str):
                # Check if reference exists
                exists = await self.get(org_id, value)
                if not exists:
                    warnings.append(f"Referenced object not found: {key}={value}")
        return warnings

    def _translate_where(
        self,
        where: Dict[str, Any],
    ) -> List[Any]:
        """
        Translate MongoDB-style query to SQLAlchemy conditions.

        Supported operators:
        - $eq, $ne: equality
        - $gt, $gte, $lt, $lte: comparison
        - $in, $nin: list membership
        - $contains: array contains
        - $exists: field exists
        - $regex: pattern match
        """
        from sqlalchemy import Float, Integer

        conditions = []

        for field, condition in where.items():
            # Get the JSONB path
            json_field = WorkspaceObject.data[field]

            if isinstance(condition, dict):
                for op, value in condition.items():
                    if op == "$eq":
                        conditions.append(json_field.astext == str(value))
                    elif op == "$ne":
                        conditions.append(json_field.astext != str(value))
                    elif op in ("$gt", "$gte", "$lt", "$lte"):
                        # Determine cast type based on value
                        if isinstance(value, int):
                            cast_type = Integer
                        elif isinstance(value, float):
                            cast_type = Float
                        else:
                            # For strings (including ISO dates), use text comparison
                            # ISO8601 dates compare correctly as strings lexicographically
                            cast_type = None

                        if cast_type:
                            casted_field = json_field.astext.cast(cast_type)
                        else:
                            casted_field = json_field.astext

                        if op == "$gt":
                            conditions.append(casted_field > value)
                        elif op == "$gte":
                            conditions.append(casted_field >= value)
                        elif op == "$lt":
                            conditions.append(casted_field < value)
                        elif op == "$lte":
                            conditions.append(casted_field <= value)
                    elif op == "$in":
                        conditions.append(json_field.astext.in_([str(v) for v in value]))
                    elif op == "$nin":
                        conditions.append(~json_field.astext.in_([str(v) for v in value]))
                    elif op == "$exists":
                        if value:
                            conditions.append(json_field.isnot(None))
                        else:
                            conditions.append(json_field.is_(None))
                    elif op == "$regex":
                        conditions.append(json_field.astext.op("~")(value))
                    elif op == "$contains":
                        # For array fields in JSONB
                        conditions.append(json_field.contains([value]))
            else:
                # Simple equality
                conditions.append(json_field.astext == str(condition))

        return conditions

    def _to_dict(self, obj: WorkspaceObject) -> Dict[str, Any]:
        """Convert WorkspaceObject to dict."""
        return {
            "id": str(obj.id),
            "org_id": obj.org_id,
            "type": obj.type,
            "data": obj.data,
            "tags": obj.tags or [],
            "created_by_type": obj.created_by_type,
            "created_by_id": obj.created_by_id,
            "created_at": obj.created_at.isoformat() if obj.created_at else None,
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
        }
