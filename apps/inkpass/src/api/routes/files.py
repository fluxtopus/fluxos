"""File routes for Den file management."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import quote

from src.database.database import get_db
from src.middleware.auth_middleware import get_auth_context, AuthContext, require_permission
from src.services.file_service import FileService, StorageQuotaExceededError, FileNotFoundError as DenFileNotFoundError
from src.services.storage import LocalStorage, BunnyStorage
from src.schemas.file import FileResponse, FileListResponse, FileDownloadUrlResponse
from src.config import settings
from src.middleware.service_auth import require_service_api_key


router = APIRouter()


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition header value safe for non-ASCII filenames."""
    # ASCII-safe fallback: replace non-latin-1 chars
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    # RFC 5987 UTF-8 encoded filename for modern browsers
    utf8_name = quote(filename)
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"


def get_storage_backend():
    """Get the configured storage backend."""
    if settings.STORAGE_BACKEND == "bunny" and settings.BUNNY_API_KEY:
        return BunnyStorage(
            api_key=settings.BUNNY_API_KEY,
            storage_zone=settings.BUNNY_STORAGE_ZONE,
            storage_hostname=settings.BUNNY_STORAGE_HOSTNAME,
            cdn_hostname=settings.BUNNY_CDN_HOSTNAME or None,
            token_key=settings.BUNNY_TOKEN_KEY or None,
        )
    return LocalStorage(storage_path=settings.LOCAL_STORAGE_PATH)


def get_file_service(db: Session = Depends(get_db)) -> FileService:
    """Dependency to get FileService instance."""
    storage = get_storage_backend()
    return FileService(db, storage)


require_agent_service_key = require_service_api_key()
# Backward-compatible alias used by some tests/imports.
validate_service_api_key = require_agent_service_key


# ==================== User Endpoints ====================


@router.post("", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_path: str = Query("/", description="Virtual folder path"),
    tags: Optional[List[str]] = Query(None, description="Tags for categorization"),
    is_public: bool = Query(False, description="Make file CDN-accessible"),
    _perm: None = Depends(require_permission("files", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Upload a new file. Requires files:create permission."""

    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_BYTES} bytes"
        )

    try:
        result = file_service.create_file(
            org_id=auth_context.user.organization_id,
            name=file.filename or "unnamed",
            file_data=file.file,
            content_type=file.content_type or "application/octet-stream",
            folder_path=folder_path,
            tags=tags or [],
            is_public=is_public,
            created_by_user_id=auth_context.user.id,
        )

        # Generate embedding in background for semantic search
        background_tasks.add_task(
            file_service.generate_file_embedding,
            result.id,
            auth_context.user.organization_id,
        )

        return result
    except StorageQuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))


@router.get("", response_model=FileListResponse)
async def list_files(
    folder_path: Optional[str] = Query(None, description="Filter by folder"),
    tags: Optional[List[str]] = Query(None, description="Filter by tags"),
    search: Optional[str] = Query(None, description="Filename search (ILIKE pattern)"),
    semantic_search: Optional[str] = Query(None, description="Semantic search using AI embeddings"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    _perm: None = Depends(require_permission("files", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """
    List files in organization. Requires files:view permission.

    Supports filename search with `search` parameter (ILIKE pattern matching)
    and semantic search with `semantic_search` parameter (AI-powered similarity).
    """

    # Use search method if any search parameters provided
    if search or semantic_search:
        return await file_service.search_files(
            org_id=auth_context.user.organization_id,
            search=search,
            semantic_search=semantic_search,
            folder_path=folder_path,
            tags=tags,
            limit=limit,
            offset=offset,
        )

    return file_service.list_files(
        org_id=auth_context.user.organization_id,
        folder_path=folder_path,
        tags=tags,
        limit=limit,
        offset=offset,
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: str,
    _perm: None = Depends(require_permission("files", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Get file metadata. Requires files:view permission."""

    file = file_service.get_file(file_id, auth_context.user.organization_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return file


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    _perm: None = Depends(require_permission("files", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Download file content. Requires files:view permission."""

    try:
        data, content_type, filename = file_service.download_file(
            file_id,
            auth_context.user.organization_id,
            auth_context.user.id
        )

        return StreamingResponse(
            data,
            media_type=content_type,
            headers={"Content-Disposition": _content_disposition(filename)}
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/{file_id}/url", response_model=FileDownloadUrlResponse)
async def get_download_url(
    file_id: str,
    expires_in: int = Query(3600, le=86400, description="URL expiration in seconds"),
    _perm: None = Depends(require_permission("files", "view")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Get temporary download URL. Requires files:view permission."""

    try:
        url = file_service.get_download_url(
            file_id,
            auth_context.user.organization_id,
            expires_in
        )
        return FileDownloadUrlResponse(url=url, expires_in=expires_in)
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.post("/{file_id}/duplicate", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_file(
    file_id: str,
    new_name: Optional[str] = Query(None),
    new_folder: Optional[str] = Query(None),
    _perm: None = Depends(require_permission("files", "create")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Duplicate a file. Requires files:create permission."""

    try:
        return file_service.duplicate_file(
            file_id,
            auth_context.user.organization_id,
            new_name,
            new_folder,
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    except StorageQuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    hard_delete: bool = Query(False, description="Permanently delete file"),
    _perm: None = Depends(require_permission("files", "delete")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Delete a file. Requires files:delete permission."""

    try:
        file_service.delete_file(
            file_id,
            auth_context.user.organization_id,
            hard_delete,
            auth_context.user.id,
        )
        return {"deleted": True}
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.patch("/{file_id}/move", response_model=FileResponse)
async def move_file(
    file_id: str,
    new_folder: Optional[str] = Query(None, description="New folder path"),
    new_name: Optional[str] = Query(None, description="New file name"),
    _perm: None = Depends(require_permission("files", "manage")),
    auth_context: AuthContext = Depends(get_auth_context),
    file_service: FileService = Depends(get_file_service),
):
    """Move and/or rename a file. Requires files:manage permission."""

    if new_folder is None and new_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of new_folder or new_name must be provided",
        )

    try:
        return file_service.move_file(
            file_id,
            auth_context.user.organization_id,
            new_folder,
            new_name,
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


# ==================== Agent Endpoints (Service Account Auth) ====================


@router.post("/agent", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def agent_upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    org_id: str = Query(..., description="Organization ID"),
    workflow_id: str = Query(..., description="Workflow ID"),
    agent_id: str = Query(..., description="Agent identifier"),
    folder_path: str = Query("/agent-outputs", description="Folder path"),
    tags: Optional[List[str]] = Query(None),
    is_public: bool = Query(False),
    is_temporary: bool = Query(False),
    expires_in_hours: Optional[int] = Query(None, ge=1, le=8760),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """
    Agent file upload endpoint (service account auth).
    Used by Tentackl agents to create files programmatically.
    """
    # Check file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {settings.MAX_FILE_SIZE_BYTES} bytes"
        )

    expires_at = None
    if expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)

    try:
        result = file_service.create_file(
            org_id=org_id,
            name=file.filename or "unnamed",
            file_data=file.file,
            content_type=file.content_type or "application/octet-stream",
            folder_path=folder_path,
            tags=tags or [],
            is_public=is_public,
            is_temporary=is_temporary,
            created_by_agent=f"workflow:{workflow_id}:agent:{agent_id}",
            workflow_id=workflow_id,
            expires_at=expires_at,
        )

        # Generate embedding in background for semantic search (skip for temp files)
        if not is_temporary:
            background_tasks.add_task(
                file_service.generate_file_embedding,
                result.id,
                org_id,
            )

        return result
    except StorageQuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))


@router.get("/agent/list", response_model=FileListResponse)
async def agent_list_files(
    org_id: str = Query(..., description="Organization ID"),
    workflow_id: Optional[str] = Query(None),
    folder_path: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    search: Optional[str] = Query(None, description="Filename search (ILIKE pattern)"),
    semantic_search: Optional[str] = Query(None, description="Semantic search using AI embeddings"),
    include_temporary: bool = Query(True),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """
    Agent file listing endpoint.

    Supports filename search with `search` parameter and semantic search with `semantic_search`.
    """
    # Use search method if any search parameters provided
    if search or semantic_search:
        return await file_service.search_files(
            org_id=org_id,
            search=search,
            semantic_search=semantic_search,
            folder_path=folder_path,
            tags=tags,
            workflow_id=workflow_id,
            include_temporary=include_temporary,
            limit=limit,
            offset=offset,
        )

    return file_service.list_files(
        org_id=org_id,
        folder_path=folder_path,
        tags=tags,
        workflow_id=workflow_id,
        include_temporary=include_temporary,
        limit=limit,
    )


@router.get("/agent/{file_id}/download")
async def agent_download_file(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    agent_id: str = Query("system", description="Agent identifier"),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """Agent file download endpoint."""
    try:
        data, content_type, filename = file_service.download_file(
            file_id, org_id, f"agent:{agent_id}"
        )

        return StreamingResponse(
            data,
            media_type=content_type,
            headers={"Content-Disposition": _content_disposition(filename)}
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/agent/{file_id}/url", response_model=FileDownloadUrlResponse)
async def agent_get_download_url(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    expires_in: int = Query(3600, le=86400),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """Agent get download URL endpoint."""
    try:
        url = file_service.get_download_url(file_id, org_id, expires_in)
        return FileDownloadUrlResponse(url=url, expires_in=expires_in)
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.delete("/agent/{file_id}")
async def agent_delete_file(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    agent_id: str = Query(..., description="Agent identifier"),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """
    Agent file deletion endpoint.
    Agents can only delete files they created or temporary files.
    """
    file = file_service.get_file(file_id, org_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Permission check: agents can only delete their own files or temp files
    agent_key = f":agent:{agent_id}"
    if not file.is_temporary and (not file.created_by_agent or agent_key not in file.created_by_agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent can only delete its own files or temporary files"
        )

    try:
        file_service.delete_file(
            file_id,
            org_id,
            hard_delete=file.is_temporary,  # Hard delete temp files
            deleted_by=f"agent:{agent_id}",
        )
        return {"deleted": True}
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")


@router.get("/agent/{file_id}", response_model=FileResponse)
async def agent_get_file(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """Get file metadata (agent endpoint)."""
    file = file_service.get_file(file_id, org_id)
    if not file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return file


@router.post("/agent/{file_id}/duplicate", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def agent_duplicate_file(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    agent_id: str = Query(..., description="Agent identifier"),
    new_name: Optional[str] = Query(None, description="New file name"),
    new_folder: Optional[str] = Query(None, description="New folder path"),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """Duplicate a file (agent endpoint)."""
    try:
        return file_service.duplicate_file(
            file_id,
            org_id,
            new_name,
            new_folder,
            created_by_agent=f"agent:{agent_id}",
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    except StorageQuotaExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))


@router.patch("/agent/{file_id}/move", response_model=FileResponse)
async def agent_move_file(
    file_id: str,
    org_id: str = Query(..., description="Organization ID"),
    new_folder: Optional[str] = Query(None, description="New folder path"),
    new_name: Optional[str] = Query(None, description="New file name"),
    service_name: str = Depends(require_agent_service_key),
    file_service: FileService = Depends(get_file_service),
):
    """Move/rename a file (agent endpoint)."""

    if new_folder is None and new_name is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of new_folder or new_name must be provided",
        )

    try:
        return file_service.move_file(
            file_id,
            org_id,
            new_folder,
            new_name,
        )
    except DenFileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
