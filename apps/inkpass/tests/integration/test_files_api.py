"""Integration tests for Files API endpoints."""

import pytest
from fastapi import status
from io import BytesIO
import os


# auth_token and auth_headers fixtures are defined in conftest.py


class TestFileUpload:
    """Test file upload endpoints."""

    @pytest.mark.integration
    def test_upload_file_success(self, client, db, auth_headers):
        """Test successful file upload."""
        file_content = b"test file content for integration test"
        files = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        response = client.post(
            "/api/v1/files",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "test.txt"
        assert data["content_type"] == "text/plain"
        assert data["size_bytes"] == len(file_content)
        assert data["folder_path"] == "/"
        assert data["status"] == "active"
        assert "id" in data

    @pytest.mark.integration
    def test_upload_file_with_folder(self, client, db, auth_headers):
        """Test file upload to specific folder."""
        file_content = b"folder file content"
        files = {"file": ("document.pdf", BytesIO(file_content), "application/pdf")}

        response = client.post(
            "/api/v1/files?folder_path=/documents/reports",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["folder_path"] == "/documents/reports"

    @pytest.mark.integration
    def test_upload_file_with_tags(self, client, db, auth_headers):
        """Test file upload with tags."""
        file_content = b"tagged content"
        files = {"file": ("tagged.txt", BytesIO(file_content), "text/plain")}

        response = client.post(
            "/api/v1/files?tags=important&tags=report",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert set(data["tags"]) == {"important", "report"}

    @pytest.mark.integration
    def test_upload_file_public(self, client, db, auth_headers):
        """Test public file upload."""
        file_content = b"public content"
        files = {"file": ("public.png", BytesIO(file_content), "image/png")}

        response = client.post(
            "/api/v1/files?is_public=true",
            files=files,
            headers=auth_headers,
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["is_public"] is True

    @pytest.mark.integration
    def test_upload_file_unauthorized(self, client, db):
        """Test upload without auth fails."""
        file_content = b"unauthorized"
        files = {"file": ("test.txt", BytesIO(file_content), "text/plain")}

        response = client.post("/api/v1/files", files=files)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestFileList:
    """Test file listing endpoints."""

    @pytest.mark.integration
    def test_list_files_empty(self, client, db, auth_headers):
        """Test listing files when none exist."""
        response = client.get("/api/v1/files", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["files"] == []
        assert data["total"] == 0

    @pytest.mark.integration
    def test_list_files_with_files(self, client, db, auth_headers):
        """Test listing uploaded files."""
        # Upload some files
        for i in range(3):
            files = {"file": (f"file{i}.txt", BytesIO(b"content"), "text/plain")}
            client.post("/api/v1/files", files=files, headers=auth_headers)

        response = client.get("/api/v1/files", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 3
        assert len(data["files"]) == 3

    @pytest.mark.integration
    def test_list_files_filter_by_folder(self, client, db, auth_headers):
        """Test filtering files by folder."""
        # Upload to different folders
        files1 = {"file": ("doc1.txt", BytesIO(b"content1"), "text/plain")}
        client.post("/api/v1/files?folder_path=/docs", files=files1, headers=auth_headers)

        files2 = {"file": ("img1.png", BytesIO(b"content2"), "image/png")}
        client.post("/api/v1/files?folder_path=/images", files=files2, headers=auth_headers)

        # Filter by folder
        response = client.get("/api/v1/files?folder_path=/docs", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert data["files"][0]["folder_path"] == "/docs"

    @pytest.mark.integration
    def test_list_files_pagination(self, client, db, auth_headers):
        """Test file listing pagination."""
        # Upload 5 files
        for i in range(5):
            files = {"file": (f"file{i}.txt", BytesIO(b"content"), "text/plain")}
            client.post("/api/v1/files", files=files, headers=auth_headers)

        # Get first page
        response = client.get("/api/v1/files?limit=2&offset=0", headers=auth_headers)
        data = response.json()
        assert len(data["files"]) == 2
        assert data["total"] == 5

        # Get second page
        response = client.get("/api/v1/files?limit=2&offset=2", headers=auth_headers)
        data = response.json()
        assert len(data["files"]) == 2


class TestFileGet:
    """Test file get endpoint."""

    @pytest.mark.integration
    def test_get_file_success(self, client, db, auth_headers):
        """Test getting file metadata."""
        # Upload a file
        files = {"file": ("test.txt", BytesIO(b"test content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        # Get file
        response = client.get(f"/api/v1/files/{file_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == file_id
        assert data["name"] == "test.txt"

    @pytest.mark.integration
    def test_get_file_not_found(self, client, db, auth_headers):
        """Test getting nonexistent file."""
        response = client.get(
            "/api/v1/files/00000000-0000-0000-0000-000000000000",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestFileDownload:
    """Test file download endpoints."""

    @pytest.mark.integration
    def test_download_file_success(self, client, db, auth_headers):
        """Test downloading file content."""
        content = b"downloadable content"
        files = {"file": ("download.txt", BytesIO(content), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.content == content
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    @pytest.mark.integration
    def test_download_file_not_found(self, client, db, auth_headers):
        """Test downloading nonexistent file."""
        response = client.get(
            "/api/v1/files/00000000-0000-0000-0000-000000000000/download",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.integration
    def test_get_download_url(self, client, db, auth_headers):
        """Test getting download URL."""
        files = {"file": ("urltest.txt", BytesIO(b"content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.get(
            f"/api/v1/files/{file_id}/url?expires_in=3600",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "url" in data
        assert data["expires_in"] == 3600


class TestFileDuplicate:
    """Test file duplicate endpoint."""

    @pytest.mark.integration
    def test_duplicate_file_success(self, client, db, auth_headers):
        """Test duplicating a file."""
        files = {"file": ("original.txt", BytesIO(b"original content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.post(
            f"/api/v1/files/{file_id}/duplicate?new_name=copy.txt",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "copy.txt"
        assert data["id"] != file_id

    @pytest.mark.integration
    def test_duplicate_file_to_new_folder(self, client, db, auth_headers):
        """Test duplicating file to different folder."""
        files = {"file": ("original.txt", BytesIO(b"content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.post(
            f"/api/v1/files/{file_id}/duplicate?new_folder=/backup",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["folder_path"] == "/backup"


class TestFileDelete:
    """Test file delete endpoints."""

    @pytest.mark.integration
    def test_delete_file_soft(self, client, db, auth_headers):
        """Test soft deleting a file."""
        files = {"file": ("delete.txt", BytesIO(b"to delete"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.delete(f"/api/v1/files/{file_id}", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["deleted"] is True

        # File should no longer be found
        get_response = client.get(f"/api/v1/files/{file_id}", headers=auth_headers)
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.integration
    def test_delete_file_hard(self, client, db, auth_headers):
        """Test hard deleting a file."""
        files = {"file": ("harddelete.txt", BytesIO(b"hard delete"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.delete(
            f"/api/v1/files/{file_id}?hard_delete=true",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["deleted"] is True


class TestFileMove:
    """Test file move endpoint."""

    @pytest.mark.integration
    def test_move_file_success(self, client, db, auth_headers):
        """Test moving a file."""
        files = {"file": ("move.txt", BytesIO(b"content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.patch(
            f"/api/v1/files/{file_id}/move?new_folder=/archive",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["folder_path"] == "/archive"

    @pytest.mark.integration
    def test_move_file_with_rename(self, client, db, auth_headers):
        """Test moving and renaming a file."""
        files = {"file": ("original.txt", BytesIO(b"content"), "text/plain")}
        upload_response = client.post("/api/v1/files", files=files, headers=auth_headers)
        file_id = upload_response.json()["id"]

        response = client.patch(
            f"/api/v1/files/{file_id}/move?new_folder=/archive&new_name=renamed.txt",
            headers=auth_headers
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["folder_path"] == "/archive"
        assert data["name"] == "renamed.txt"


class TestServiceAccountAuth:
    """Test service account authentication for agent endpoints."""

    @pytest.fixture
    def service_headers(self, monkeypatch):
        """Set up service API key for testing."""
        monkeypatch.setenv("SERVICE_API_KEYS", "tentackl:test-service-key-123")
        return {"X-Service-API-Key": "test-service-key-123"}

    @pytest.mark.integration
    def test_agent_upload_missing_key(self, client, db):
        """Test agent upload without service key fails."""
        files = {"file": ("test.txt", BytesIO(b"content"), "text/plain")}

        response = client.post(
            "/api/v1/files/agent?org_id=00000000-0000-0000-0000-000000000000&workflow_id=wf-1&agent_id=agent-1",
            files=files,
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.integration
    def test_agent_upload_invalid_key(self, client, db):
        """Test agent upload with invalid service key fails."""
        files = {"file": ("test.txt", BytesIO(b"content"), "text/plain")}

        response = client.post(
            "/api/v1/files/agent?org_id=00000000-0000-0000-0000-000000000000&workflow_id=wf-1&agent_id=agent-1",
            files=files,
            headers={"X-Service-API-Key": "invalid-key"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
