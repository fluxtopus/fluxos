"""inkPass File Management Client implementation."""

from io import BytesIO
from typing import Any, BinaryIO, List, Optional
from uuid import UUID

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import InkPassConfig
from .exceptions import (
    InkPassError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

logger = structlog.get_logger()


class FileClient:
    """
    Async client for inkPass file management service.

    This client provides file upload, download, and management operations
    for service-to-service communication using service API keys.

    Example:
        ```python
        from inkpass_sdk import FileClient, InkPassConfig
        from uuid import UUID

        # Initialize with service API key
        config = InkPassConfig(
            base_url="http://inkpass:8002",
            api_key="your-service-api-key"
        )
        client = FileClient(config)

        # Upload a file from an agent
        with open("output.json", "rb") as f:
            result = await client.upload(
                org_id=UUID("..."),
                workflow_id="workflow-123",
                agent_id="data-processor-1",
                file_data=f,
                filename="output.json",
                content_type="application/json",
            )

        # Download a file
        file_data = await client.download(
            org_id=UUID("..."),
            file_id=UUID("..."),
        )
        ```
    """

    def __init__(self, config: InkPassConfig | None = None) -> None:
        """
        Initialize file client.

        Args:
            config: Client configuration with base_url and service API key.
                   If None, uses default config.
        """
        self.config = config or InkPassConfig()
        self._client: httpx.AsyncClient | None = None
        logger.info("FileClient initialized", base_url=self.config.base_url)

    async def __aenter__(self) -> "FileClient":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(300.0),  # 5 minutes for file uploads
            verify=self.config.verify_ssl,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(300.0),  # 5 minutes for file uploads
                verify=self.config.verify_ssl,
            )
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """
        Get request headers with service API key.

        Returns:
            Headers dictionary with X-Service-API-Key

        Raises:
            ValidationError: If service API key is not configured
        """
        if not self.config.api_key:
            raise ValidationError("Service API key is required for file operations")

        return {"X-Service-API-Key": self.config.api_key}

    def _handle_error(self, response: httpx.Response) -> None:
        """
        Handle HTTP error responses.

        Args:
            response: HTTP response

        Raises:
            PermissionDeniedError: For 403 responses
            ResourceNotFoundError: For 404 responses
            ValidationError: For 400/422 responses
            ServiceUnavailableError: For 503 responses
            InkPassError: For other errors
        """
        status_code = response.status_code

        try:
            error_data = response.json()
            message = error_data.get("detail", response.text)
        except Exception:
            message = response.text

        if status_code == 400:
            raise ValidationError(message)
        elif status_code == 403:
            raise PermissionDeniedError(message)
        elif status_code == 404:
            raise ResourceNotFoundError(message)
        elif status_code == 422:
            raise ValidationError(message)
        elif status_code == 503:
            raise ServiceUnavailableError(message)
        else:
            raise InkPassError(message, status_code=status_code)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def upload(
        self,
        org_id: UUID,
        workflow_id: str,
        agent_id: str,
        file_data: BinaryIO,
        filename: str,
        content_type: str = "application/octet-stream",
        folder_path: str = "/agent-outputs",
        tags: Optional[List[str]] = None,
        is_public: bool = False,
        is_temporary: bool = False,
        expires_in_hours: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Upload a file from an agent.

        Args:
            org_id: Organization UUID
            workflow_id: Workflow identifier
            agent_id: Agent identifier
            file_data: File binary data
            filename: Name of the file
            content_type: MIME type of the file
            folder_path: Virtual folder path (default: /agent-outputs)
            tags: Optional list of tags for categorization
            is_public: Whether file should be publicly accessible
            is_temporary: Whether file should be marked as temporary
            expires_in_hours: Optional expiration time in hours

        Returns:
            Dict with file metadata including file_id, url, etc.

        Raises:
            ValidationError: If input validation fails or API key missing
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            # Build query parameters
            params: dict[str, Any] = {
                "org_id": str(org_id),
                "workflow_id": workflow_id,
                "agent_id": agent_id,
                "folder_path": folder_path,
                "is_public": str(is_public).lower(),
                "is_temporary": str(is_temporary).lower(),
            }

            if expires_in_hours is not None:
                params["expires_in_hours"] = str(expires_in_hours)

            if tags:
                params["tags"] = tags

            # Prepare multipart file upload
            files = {"file": (filename, file_data, content_type)}

            response = await client.post(
                "/api/v1/files/agent",
                headers=self._get_headers(),
                params=params,
                files=files,
            )

            if response.status_code in (200, 201):
                logger.info(
                    "File uploaded successfully",
                    filename=filename,
                    workflow_id=workflow_id,
                    agent_id=agent_id,
                )
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File upload request failed", error=str(e), filename=filename)
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file upload")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def download(self, org_id: UUID, file_id: UUID, agent_id: Optional[str] = None) -> BinaryIO:
        """
        Download a file.

        Args:
            org_id: Organization UUID
            file_id: File UUID to download
            agent_id: Agent identifier (required for agent endpoints)

        Returns:
            BinaryIO object containing file data

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            params: dict[str, Any] = {"org_id": str(org_id)}
            if agent_id:
                params["agent_id"] = agent_id

            response = await client.get(
                f"/api/v1/files/agent/{file_id}/download",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 200:
                logger.info("File downloaded successfully", file_id=str(file_id))
                return BytesIO(response.content)
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File download request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file download")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_download_url(
        self,
        org_id: UUID,
        file_id: UUID,
        expires_in: int = 3600,
    ) -> str:
        """
        Get a temporary download URL for a file.

        Args:
            org_id: Organization UUID
            file_id: File UUID
            expires_in: URL expiration time in seconds (default: 3600)

        Returns:
            Temporary download URL string

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/files/agent/{file_id}/url",
                headers=self._get_headers(),
                params={"org_id": str(org_id), "expires_in": str(expires_in)},
            )

            if response.status_code == 200:
                logger.info("Download URL generated", file_id=str(file_id), expires_in=expires_in)
                return response.json()["url"]
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Download URL request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during download URL generation")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def list_files(
        self,
        org_id: UUID,
        workflow_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[dict[str, Any]]:
        """
        List files available to agents.

        Args:
            org_id: Organization UUID
            workflow_id: Optional workflow ID to filter by
            folder_path: Optional folder path to filter by
            tags: Optional list of tags to filter by

        Returns:
            List of file metadata dictionaries

        Raises:
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            # Build query parameters
            params: dict[str, Any] = {"org_id": str(org_id)}

            if workflow_id:
                params["workflow_id"] = workflow_id
            if folder_path:
                params["folder_path"] = folder_path
            if tags:
                params["tags"] = tags

            response = await client.get(
                "/api/v1/files/agent/list",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 200:
                data = response.json()
                # API returns FileListResponse with "files" key for paginated results
                if isinstance(data, dict) and "files" in data:
                    files = data["files"]
                else:
                    files = data if isinstance(data, list) else []
                logger.info("Files listed successfully", count=len(files), org_id=str(org_id))
                return files
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File listing request failed", error=str(e), org_id=str(org_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file listing")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def delete(
        self,
        org_id: UUID,
        file_id: UUID,
        agent_id: str,
    ) -> bool:
        """
        Delete a file.

        Args:
            org_id: Organization UUID
            file_id: File UUID to delete
            agent_id: Agent identifier requesting deletion

        Returns:
            True if deletion successful

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.delete(
                f"/api/v1/files/agent/{file_id}",
                headers=self._get_headers(),
                params={"org_id": str(org_id), "agent_id": agent_id},
            )

            if response.status_code in (200, 204):
                logger.info("File deleted successfully", file_id=str(file_id), agent_id=agent_id)
                return True
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File deletion request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file deletion")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def get_file(self, org_id: UUID, file_id: UUID) -> dict[str, Any]:
        """
        Get file metadata.

        Args:
            org_id: Organization UUID
            file_id: File UUID

        Returns:
            Dict with file metadata

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            response = await client.get(
                f"/api/v1/files/agent/{file_id}",
                headers=self._get_headers(),
                params={"org_id": str(org_id)},
            )

            if response.status_code == 200:
                logger.info("File metadata retrieved", file_id=str(file_id))
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("Get file request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during get file")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def duplicate(
        self,
        org_id: UUID,
        file_id: UUID,
        agent_id: str,
        new_name: Optional[str] = None,
        new_folder: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Duplicate a file.

        Args:
            org_id: Organization UUID
            file_id: File UUID to duplicate
            agent_id: Agent identifier
            new_name: Optional new name for the duplicate
            new_folder: Optional folder path for the duplicate

        Returns:
            Dict with new file metadata

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        try:
            client = self._get_client()

            params: dict[str, Any] = {
                "org_id": str(org_id),
                "agent_id": agent_id,
            }
            if new_name:
                params["new_name"] = new_name
            if new_folder:
                params["new_folder"] = new_folder

            response = await client.post(
                f"/api/v1/files/agent/{file_id}/duplicate",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code in (200, 201):
                logger.info("File duplicated successfully", file_id=str(file_id), agent_id=agent_id)
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File duplicate request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file duplication")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def move(
        self,
        org_id: UUID,
        file_id: UUID,
        new_folder: Optional[str] = None,
        new_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Move and/or rename a file.

        At least one of new_folder or new_name must be provided.

        Args:
            org_id: Organization UUID
            file_id: File UUID to move
            new_folder: New folder path (keeps current folder if None)
            new_name: New file name (keeps current name if None)

        Returns:
            Dict with updated file metadata

        Raises:
            ValidationError: If neither new_folder nor new_name is provided
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        if new_folder is None and new_name is None:
            raise ValidationError("At least one of new_folder or new_name must be provided")

        try:
            client = self._get_client()

            params: dict[str, Any] = {
                "org_id": str(org_id),
            }
            if new_folder is not None:
                params["new_folder"] = new_folder
            if new_name is not None:
                params["new_name"] = new_name

            response = await client.patch(
                f"/api/v1/files/agent/{file_id}/move",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 200:
                logger.info("File moved successfully", file_id=str(file_id))
                return response.json()
            else:
                self._handle_error(response)

        except httpx.RequestError as e:
            logger.error("File move request failed", error=str(e), file_id=str(file_id))
            raise ServiceUnavailableError(f"inkPass service unavailable: {e}")

        raise InkPassError("Unexpected error during file move")

    async def rename(
        self,
        org_id: UUID,
        file_id: UUID,
        new_name: str,
    ) -> dict[str, Any]:
        """
        Rename a file without moving it.

        Args:
            org_id: Organization UUID
            file_id: File UUID to rename
            new_name: New file name

        Returns:
            Dict with updated file metadata

        Raises:
            ResourceNotFoundError: If file not found
            PermissionDeniedError: If service lacks permission
            ServiceUnavailableError: If service is unavailable
        """
        return await self.move(org_id, file_id, new_name=new_name)

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("FileClient closed")
