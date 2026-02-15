"""
File Service for Den file management.

Provides business logic for file operations including upload, download,
duplicate, delete, and listing with multi-tenant isolation.
"""

from typing import Optional, List, BinaryIO, Tuple, TypeVar, Coroutine, Any
from datetime import datetime, timedelta
import hashlib
import uuid
import asyncio

from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.database.models import File, FileAccessLog, Organization
from src.schemas.file import FileResponse, FileListResponse
from src.services.storage.base import StorageBackend
from src.services.embedding_service import embedding_service
import structlog

logger = structlog.get_logger(__name__)


class StorageQuotaExceededError(Exception):
    """Raised when file upload would exceed organization storage quota."""
    pass


class FileNotFoundError(Exception):
    """Raised when a requested file does not exist."""
    pass


T = TypeVar('T')


def _run_sync(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine synchronously.

    Handles the case where we're already inside an async event loop
    (like FastAPI) by creating a new event loop in a thread.
    """
    try:
        # Check if there's already a running event loop
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop, safe to use asyncio.run()
        return asyncio.run(coro)

    # Already in an async context, run in a new thread to avoid blocking
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


class FileService:
    """Business logic for file management operations."""

    def __init__(self, db: Session, storage: StorageBackend):
        self.db = db
        self.storage = storage

    def create_file(
        self,
        org_id: str,
        name: str,
        file_data: BinaryIO,
        content_type: str,
        folder_path: str = "/",
        tags: List[str] = None,
        is_public: bool = False,
        is_temporary: bool = False,
        created_by_user_id: Optional[str] = None,
        created_by_agent: Optional[str] = None,
        workflow_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> FileResponse:
        """
        Create a new file in storage.

        Args:
            org_id: Organization ID
            name: File name
            file_data: File content as binary stream
            content_type: MIME type
            folder_path: Virtual folder path
            tags: Optional list of tags
            is_public: Whether file should be CDN-accessible
            is_temporary: Whether file is temporary
            created_by_user_id: User who created the file
            created_by_agent: Agent that created the file
            workflow_id: Associated workflow ID
            expires_at: Optional expiration datetime

        Returns:
            FileResponse with file metadata

        Raises:
            StorageQuotaExceededError: If upload exceeds quota
        """
        # Get organization and check quota
        org = self._get_organization(org_id)

        # Calculate file size
        file_data.seek(0, 2)
        file_size = file_data.tell()
        file_data.seek(0)

        # Check quota
        if org.storage_used_bytes + file_size > org.storage_quota_bytes:
            raise StorageQuotaExceededError(
                f"Storage quota exceeded. Used: {org.storage_used_bytes}, "
                f"Quota: {org.storage_quota_bytes}, File: {file_size}"
            )

        # Generate storage key
        storage_key = self._generate_storage_key(org_id, folder_path, name)

        # Calculate checksum
        checksum = self._calculate_checksum(file_data)
        file_data.seek(0)

        # Upload to storage (async operation wrapped)
        result = _run_sync(self.storage.upload(
            file_data=file_data,
            storage_key=storage_key,
            content_type=content_type,
            is_public=is_public
        ))

        # Create database record
        file = File(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            name=name,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=file_size,
            checksum_sha256=checksum,
            folder_path=folder_path,
            tags=tags or [],
            is_public=is_public,
            is_temporary=is_temporary,
            created_by_user_id=created_by_user_id,
            created_by_agent=created_by_agent,
            workflow_id=workflow_id,
            expires_at=expires_at,
        )

        self.db.add(file)

        # Update organization storage usage
        org.storage_used_bytes = (org.storage_used_bytes or 0) + file_size

        self.db.commit()
        self.db.refresh(file)

        # Log access
        self._log_access(
            file_id=file.id,
            org_id=org_id,
            action="create",
            accessor_id=created_by_user_id or created_by_agent or "system"
        )

        return self._to_response(file, cdn_url=result.cdn_url)

    def get_file(self, file_id: str, org_id: str) -> Optional[FileResponse]:
        """
        Get file metadata by ID.

        Args:
            file_id: File ID
            org_id: Organization ID for isolation

        Returns:
            FileResponse or None if not found
        """
        file = self.db.query(File).filter(
            and_(
                File.id == file_id,
                File.organization_id == org_id,
                File.status != "deleted"
            )
        ).first()

        if not file:
            return None

        return self._to_response(file)

    def download_file(
        self,
        file_id: str,
        org_id: str,
        accessor_id: str,
    ) -> Tuple[BinaryIO, str, str]:
        """
        Download file content.

        Args:
            file_id: File ID
            org_id: Organization ID
            accessor_id: ID of user/agent downloading

        Returns:
            Tuple of (file_data, content_type, filename)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file = self._get_file_or_raise(file_id, org_id)

        # Download from storage
        data = _run_sync(self.storage.download(file.storage_key))

        # Log access
        self._log_access(file_id, org_id, "download", accessor_id)

        return data, file.content_type, file.name

    def get_download_url(
        self,
        file_id: str,
        org_id: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Get a temporary download URL.

        Args:
            file_id: File ID
            org_id: Organization ID
            expires_in: URL expiration in seconds

        Returns:
            Temporary download URL

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file = self._get_file_or_raise(file_id, org_id)

        # For public files, return CDN URL directly if available
        if file.is_public:
            return _run_sync(self.storage.get_download_url(file.storage_key, expires_in))

        return _run_sync(self.storage.get_download_url(file.storage_key, expires_in))

    def duplicate_file(
        self,
        file_id: str,
        org_id: str,
        new_name: Optional[str] = None,
        new_folder: Optional[str] = None,
        created_by_agent: Optional[str] = None,
    ) -> FileResponse:
        """
        Duplicate a file.

        Args:
            file_id: Source file ID
            org_id: Organization ID
            new_name: New file name (default: "Copy of {original}")
            new_folder: New folder path (default: same as original)
            created_by_agent: Agent performing the duplication

        Returns:
            FileResponse for the new file

        Raises:
            FileNotFoundError: If source file doesn't exist
            StorageQuotaExceededError: If duplication exceeds quota
        """
        source = self._get_file_or_raise(file_id, org_id)

        # Check quota
        org = self._get_organization(org_id)
        if org.storage_used_bytes + source.size_bytes > org.storage_quota_bytes:
            raise StorageQuotaExceededError(
                f"Storage quota exceeded. Cannot duplicate file of {source.size_bytes} bytes."
            )

        new_name = new_name or f"Copy of {source.name}"
        new_folder = new_folder or source.folder_path
        new_storage_key = self._generate_storage_key(org_id, new_folder, new_name)

        # Copy in storage
        _run_sync(self.storage.copy(source.storage_key, new_storage_key))

        # Create new database record
        new_file = File(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            name=new_name,
            storage_key=new_storage_key,
            content_type=source.content_type,
            size_bytes=source.size_bytes,
            checksum_sha256=source.checksum_sha256,
            folder_path=new_folder,
            tags=list(source.tags) if source.tags else [],
            is_public=source.is_public,
            created_by_agent=created_by_agent,
        )

        self.db.add(new_file)

        # Update storage usage
        org.storage_used_bytes = (org.storage_used_bytes or 0) + source.size_bytes

        self.db.commit()
        self.db.refresh(new_file)

        return self._to_response(new_file)

    def delete_file(
        self,
        file_id: str,
        org_id: str,
        hard_delete: bool = False,
        deleted_by: Optional[str] = None,
    ) -> bool:
        """
        Delete a file.

        Args:
            file_id: File ID
            org_id: Organization ID
            hard_delete: If True, permanently delete; otherwise soft delete
            deleted_by: ID of user/agent deleting

        Returns:
            True if deleted successfully

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file = self._get_file_or_raise(file_id, org_id)

        if hard_delete:
            # Log access BEFORE hard delete (FK constraint)
            self._log_access(file_id, org_id, "delete", deleted_by or "system")

            # Delete from storage
            _run_sync(self.storage.delete(file.storage_key))

            # Update storage usage
            org = self._get_organization(org_id)
            org.storage_used_bytes = max(0, (org.storage_used_bytes or 0) - file.size_bytes)

            # Delete from database
            self.db.delete(file)
            self.db.commit()
        else:
            # Soft delete
            file.status = "deleted"
            file.deleted_at = datetime.utcnow()
            self.db.commit()

            # Log access after soft delete
            self._log_access(file_id, org_id, "delete", deleted_by or "system")

        return True

    def move_file(
        self,
        file_id: str,
        org_id: str,
        new_folder: Optional[str] = None,
        new_name: Optional[str] = None,
    ) -> FileResponse:
        """
        Move and/or rename a file (metadata only).

        Args:
            file_id: File ID
            org_id: Organization ID
            new_folder: New folder path (keeps current folder if None)
            new_name: New file name (keeps current name if None)

        Returns:
            Updated FileResponse

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If neither new_folder nor new_name is provided
        """
        if new_folder is None and new_name is None:
            raise ValueError("At least one of new_folder or new_name must be provided")

        file = self._get_file_or_raise(file_id, org_id)

        if new_folder is not None:
            # Normalize folder path
            if not new_folder.startswith("/"):
                new_folder = "/" + new_folder
            new_folder = new_folder.rstrip("/") if len(new_folder) > 1 else new_folder
            file.folder_path = new_folder

        if new_name:
            file.name = new_name
        file.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(file)

        return self._to_response(file)

    def list_files(
        self,
        org_id: str,
        folder_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        include_temporary: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> FileListResponse:
        """
        List files with filters.

        Args:
            org_id: Organization ID
            folder_path: Filter by folder
            tags: Filter by tags (files must have ALL specified tags)
            workflow_id: Filter by workflow ID
            include_temporary: Include temporary files
            limit: Max results
            offset: Pagination offset

        Returns:
            FileListResponse with files and pagination info
        """
        query = self.db.query(File).filter(
            and_(
                File.organization_id == org_id,
                File.status == "active"
            )
        )

        if folder_path:
            query = query.filter(File.folder_path == folder_path)

        if tags:
            # Files must contain all specified tags
            query = query.filter(File.tags.contains(tags))

        if workflow_id:
            query = query.filter(File.workflow_id == workflow_id)

        if not include_temporary:
            query = query.filter(File.is_temporary == False)

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        files = query.order_by(File.created_at.desc()).limit(limit).offset(offset).all()

        return FileListResponse(
            files=[self._to_response(f) for f in files],
            total=total,
            limit=limit,
            offset=offset
        )

    async def search_files(
        self,
        org_id: str,
        search: Optional[str] = None,
        semantic_search: Optional[str] = None,
        folder_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
        workflow_id: Optional[str] = None,
        include_temporary: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> FileListResponse:
        """
        Search files with filename pattern matching and/or semantic search.

        Args:
            org_id: Organization ID
            search: Filename search pattern (ILIKE %search%)
            semantic_search: Natural language query for semantic similarity
            folder_path: Filter by folder
            tags: Filter by tags (files must have ALL specified tags)
            workflow_id: Filter by workflow ID
            include_temporary: Include temporary files
            limit: Max results
            offset: Pagination offset

        Returns:
            FileListResponse with search results
        """
        # Base query with organization isolation
        query = self.db.query(File).filter(
            and_(
                File.organization_id == org_id,
                File.status == "active"
            )
        )

        # Apply standard filters
        if folder_path:
            query = query.filter(File.folder_path == folder_path)
        if tags:
            query = query.filter(File.tags.contains(tags))
        if workflow_id:
            query = query.filter(File.workflow_id == workflow_id)
        if not include_temporary:
            query = query.filter(File.is_temporary == False)

        # Apply filename search (ILIKE pattern matching)
        if search:
            query = query.filter(File.name.ilike(f"%{search}%"))

        # Apply semantic search if provided
        if semantic_search:
            # Generate embedding for the search query
            query_embedding = await embedding_service.generate_embedding(semantic_search)

            if query_embedding:
                # Filter to only files with embeddings
                query = query.filter(File.embedding.isnot(None))

                # Order by cosine distance (smaller = more similar)
                query = query.order_by(File.embedding.cosine_distance(query_embedding))

                logger.debug(
                    "semantic_search_executed",
                    query=semantic_search[:50],
                    org_id=org_id
                )
            else:
                # Embedding generation failed, fall back to regular ordering
                logger.warning("semantic_search_embedding_failed", query=semantic_search[:50])
                query = query.order_by(File.created_at.desc())
        else:
            # No semantic search, order by creation date
            query = query.order_by(File.created_at.desc())

        # Get total count (approximate for semantic search)
        total = query.count()

        # Apply pagination
        files = query.limit(limit).offset(offset).all()

        return FileListResponse(
            files=[self._to_response(f) for f in files],
            total=total,
            limit=limit,
            offset=offset
        )

    async def generate_file_embedding(self, file_id: str, org_id: str) -> bool:
        """
        Generate and store embedding for a file.

        Called asynchronously after file creation.

        Args:
            file_id: File ID
            org_id: Organization ID

        Returns:
            True if embedding was generated successfully
        """
        if not embedding_service.is_enabled():
            logger.debug("embedding_service_disabled")
            return False

        try:
            file = self._get_file_or_raise(file_id, org_id)

            # Update status to processing
            file.embedding_status = "processing"
            self.db.commit()

            # Build searchable text from file metadata
            text = embedding_service.build_searchable_text(
                filename=file.name,
                folder_path=file.folder_path,
                tags=file.tags or [],
                content_type=file.content_type
            )

            # Generate embedding
            embedding = await embedding_service.generate_embedding(text)

            if embedding:
                file.embedding = embedding
                file.embedding_status = "completed"
                logger.info(
                    "file_embedding_generated",
                    file_id=file_id,
                    filename=file.name
                )
            else:
                file.embedding_status = "failed"
                logger.warning(
                    "file_embedding_failed",
                    file_id=file_id,
                    filename=file.name
                )

            self.db.commit()
            return file.embedding_status == "completed"

        except Exception as e:
            logger.error(
                "file_embedding_error",
                file_id=file_id,
                error=str(e)
            )
            try:
                file = self.db.query(File).filter(File.id == file_id).first()
                if file:
                    file.embedding_status = "failed"
                    self.db.commit()
            except Exception:
                pass
            return False

    # Helper methods

    def _generate_storage_key(self, org_id: str, folder_path: str, name: str) -> str:
        """Generate a unique storage key."""
        unique_id = str(uuid.uuid4())[:8]
        clean_folder = folder_path.strip("/")
        if clean_folder:
            return f"{org_id}/{clean_folder}/{unique_id}_{name}"
        return f"{org_id}/{unique_id}_{name}"

    def _get_organization(self, org_id: str) -> Organization:
        """Get organization by ID."""
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError(f"Organization not found: {org_id}")
        return org

    def _get_file_or_raise(self, file_id: str, org_id: str) -> File:
        """Get file or raise FileNotFoundError."""
        file = self.db.query(File).filter(
            and_(
                File.id == file_id,
                File.organization_id == org_id,
                File.status != "deleted"
            )
        ).first()

        if not file:
            raise FileNotFoundError(f"File not found: {file_id}")
        return file

    def _log_access(
        self,
        file_id: str,
        org_id: str,
        action: str,
        accessor_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log file access for audit trail."""
        # Determine accessor type
        if accessor_id.startswith("workflow:") or accessor_id.startswith("agent:"):
            accessor_type = "agent"
        elif accessor_id == "system":
            accessor_type = "service"
        else:
            accessor_type = "user"

        log = FileAccessLog(
            id=str(uuid.uuid4()),
            file_id=file_id,
            organization_id=org_id,
            action=action,
            accessor_type=accessor_type,
            accessor_id=accessor_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(log)
        self.db.commit()

    def _calculate_checksum(self, file_data: BinaryIO) -> str:
        """Calculate SHA-256 checksum of file data."""
        sha256 = hashlib.sha256()
        file_data.seek(0)
        for chunk in iter(lambda: file_data.read(8192), b""):
            sha256.update(chunk)
        file_data.seek(0)
        return sha256.hexdigest()

    def _to_response(self, file: File, cdn_url: Optional[str] = None) -> FileResponse:
        """Convert File model to FileResponse schema."""
        return FileResponse(
            id=file.id,
            organization_id=file.organization_id,
            name=file.name,
            storage_key=file.storage_key,
            content_type=file.content_type,
            size_bytes=file.size_bytes,
            checksum_sha256=file.checksum_sha256,
            folder_path=file.folder_path,
            tags=file.tags or [],
            custom_metadata=file.custom_metadata or {},
            created_by_user_id=file.created_by_user_id,
            created_by_agent=file.created_by_agent,
            workflow_id=file.workflow_id,
            status=file.status,
            is_temporary=file.is_temporary,
            is_public=file.is_public,
            cdn_url=cdn_url,
            created_at=file.created_at,
            updated_at=file.updated_at,
            expires_at=file.expires_at,
        )
