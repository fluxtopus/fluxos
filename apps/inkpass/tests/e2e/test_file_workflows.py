"""E2E tests for complete file workflows.

Tests complete user and agent file operations including:
- User upload -> Agent read -> Agent output flow
- Storage quota enforcement
- Temporary file handling
"""

import pytest
from fastapi import status
from io import BytesIO
import uuid


class TestUserFileWorkflow:
    """Test complete user file workflows."""

    @pytest.mark.e2e
    def test_upload_list_download_delete_flow(self, client, db, auth_headers):
        """Test complete user file lifecycle."""
        # Step 1: Upload a file
        file_content = b"E2E test file content for workflow testing"
        files = {"file": ("workflow-test.txt", BytesIO(file_content), "text/plain")}

        upload_response = client.post(
            "/api/v1/files?folder_path=/e2e-tests&tags=e2e&tags=workflow",
            files=files,
            headers=auth_headers,
        )
        assert upload_response.status_code == status.HTTP_201_CREATED
        file_data = upload_response.json()
        file_id = file_data["id"]

        # Verify upload data
        assert file_data["name"] == "workflow-test.txt"
        assert file_data["folder_path"] == "/e2e-tests"
        assert set(file_data["tags"]) == {"e2e", "workflow"}
        assert file_data["size_bytes"] == len(file_content)
        assert file_data["status"] == "active"

        # Step 2: List files - should include our file
        list_response = client.get(
            "/api/v1/files?folder_path=/e2e-tests",
            headers=auth_headers,
        )
        assert list_response.status_code == status.HTTP_200_OK
        list_data = list_response.json()
        assert list_data["total"] >= 1
        file_ids = [f["id"] for f in list_data["files"]]
        assert file_id in file_ids

        # Step 3: Get file metadata
        get_response = client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == status.HTTP_200_OK
        assert get_response.json()["id"] == file_id

        # Step 4: Download file content
        download_response = client.get(
            f"/api/v1/files/{file_id}/download",
            headers=auth_headers,
        )
        assert download_response.status_code == status.HTTP_200_OK
        assert download_response.content == file_content

        # Step 5: Get download URL
        url_response = client.get(
            f"/api/v1/files/{file_id}/url?expires_in=300",
            headers=auth_headers,
        )
        assert url_response.status_code == status.HTTP_200_OK
        url_data = url_response.json()
        assert "url" in url_data
        assert url_data["expires_in"] == 300

        # Step 6: Soft delete file
        delete_response = client.delete(
            f"/api/v1/files/{file_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == status.HTTP_200_OK
        assert delete_response.json()["deleted"] is True

        # Step 7: Verify file is no longer accessible
        get_deleted_response = client.get(
            f"/api/v1/files/{file_id}",
            headers=auth_headers,
        )
        assert get_deleted_response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.e2e
    def test_duplicate_and_move_workflow(self, client, db, auth_headers):
        """Test file duplication and moving."""
        # Upload original file
        files = {"file": ("original.txt", BytesIO(b"original content"), "text/plain")}
        upload_response = client.post(
            "/api/v1/files?folder_path=/source",
            files=files,
            headers=auth_headers,
        )
        assert upload_response.status_code == status.HTTP_201_CREATED
        original_id = upload_response.json()["id"]

        # Duplicate file
        duplicate_response = client.post(
            f"/api/v1/files/{original_id}/duplicate?new_name=copy.txt&new_folder=/backup",
            headers=auth_headers,
        )
        assert duplicate_response.status_code == status.HTTP_201_CREATED
        copy_data = duplicate_response.json()
        assert copy_data["name"] == "copy.txt"
        assert copy_data["folder_path"] == "/backup"
        assert copy_data["id"] != original_id

        # Move original file
        move_response = client.patch(
            f"/api/v1/files/{original_id}/move?new_folder=/archive&new_name=archived.txt",
            headers=auth_headers,
        )
        assert move_response.status_code == status.HTTP_200_OK
        moved_data = move_response.json()
        assert moved_data["folder_path"] == "/archive"
        assert moved_data["name"] == "archived.txt"

        # Verify both files exist
        for file_id in [original_id, copy_data["id"]]:
            get_response = client.get(f"/api/v1/files/{file_id}", headers=auth_headers)
            assert get_response.status_code == status.HTTP_200_OK

    @pytest.mark.e2e
    def test_multiple_file_types(self, client, db, auth_headers):
        """Test uploading various file types."""
        test_files = [
            ("document.pdf", b"%PDF-1.4 test content", "application/pdf"),
            ("image.png", b"\x89PNG\r\n\x1a\n test", "image/png"),
            ("data.json", b'{"key": "value"}', "application/json"),
            ("script.py", b"print('hello')", "text/x-python"),
        ]

        uploaded_ids = []

        for filename, content, content_type in test_files:
            files = {"file": (filename, BytesIO(content), content_type)}
            response = client.post(
                "/api/v1/files?folder_path=/multi-type",
                files=files,
                headers=auth_headers,
            )
            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()
            assert data["content_type"] == content_type
            uploaded_ids.append(data["id"])

        # List all files in folder
        list_response = client.get(
            "/api/v1/files?folder_path=/multi-type",
            headers=auth_headers,
        )
        assert list_response.status_code == status.HTTP_200_OK
        assert list_response.json()["total"] >= 4

    @pytest.mark.e2e
    def test_tag_filtering(self, client, db, auth_headers):
        """Test filtering files by tags."""
        # Upload files with different tags
        for i, tags in enumerate([["important"], ["archive"], ["important", "archive"]]):
            files = {"file": (f"tagged-{i}.txt", BytesIO(b"content"), "text/plain")}
            tag_params = "&".join([f"tags={t}" for t in tags])
            response = client.post(
                f"/api/v1/files?folder_path=/tagged&{tag_params}",
                files=files,
                headers=auth_headers,
            )
            assert response.status_code == status.HTTP_201_CREATED

        # Filter by single tag
        response = client.get(
            "/api/v1/files?folder_path=/tagged&tags=important",
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_200_OK
        # Should find files with "important" tag
        data = response.json()
        for file in data["files"]:
            assert "important" in file["tags"]


class TestPublicFileWorkflow:
    """Test public file workflows for CDN delivery."""

    @pytest.mark.e2e
    def test_public_file_creation(self, client, db, auth_headers):
        """Test creating a public file."""
        files = {"file": ("public-image.png", BytesIO(b"fake png data"), "image/png")}

        response = client.post(
            "/api/v1/files?is_public=true&folder_path=/public",
            files=files,
            headers=auth_headers,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["is_public"] is True

        # Get download URL for public file
        url_response = client.get(
            f"/api/v1/files/{data['id']}/url",
            headers=auth_headers,
        )
        assert url_response.status_code == status.HTTP_200_OK
        assert "url" in url_response.json()


class TestErrorHandling:
    """Test error handling in file operations."""

    @pytest.mark.e2e
    def test_get_nonexistent_file(self, client, db, auth_headers):
        """Test accessing nonexistent file returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/files/{fake_id}", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.e2e
    def test_download_nonexistent_file(self, client, db, auth_headers):
        """Test downloading nonexistent file returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/files/{fake_id}/download", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.e2e
    def test_duplicate_nonexistent_file(self, client, db, auth_headers):
        """Test duplicating nonexistent file returns 404."""
        fake_id = str(uuid.uuid4())
        response = client.post(f"/api/v1/files/{fake_id}/duplicate", headers=auth_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.e2e
    def test_unauthorized_access(self, client, db):
        """Test accessing files without auth returns 401."""
        # GET endpoints should return 401
        response = client.get("/api/v1/files")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = client.get(f"/api/v1/files/{uuid.uuid4()}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        # POST with file should return 401 (not 422 validation error)
        files = {"file": ("test.txt", BytesIO(b"content"), "text/plain")}
        response = client.post("/api/v1/files", files=files)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAgentEndpointsE2E:
    """E2E tests for agent/service endpoints."""

    @pytest.mark.e2e
    def test_agent_endpoints_require_service_key(self, client, db):
        """Test agent endpoints reject requests without valid service key."""
        org_id = str(uuid.uuid4())
        endpoints = [
            ("POST", f"/api/v1/files/agent?org_id={org_id}&workflow_id=wf-1&agent_id=test"),
            ("GET", f"/api/v1/files/agent/list?org_id={org_id}"),
            ("GET", f"/api/v1/files/agent/{uuid.uuid4()}/download?org_id={org_id}&agent_id=test"),
            ("DELETE", f"/api/v1/files/agent/{uuid.uuid4()}?org_id={org_id}&agent_id=test"),
        ]

        for method, endpoint in endpoints:
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint)
            elif method == "DELETE":
                response = client.delete(endpoint)

            assert response.status_code == status.HTTP_401_UNAUTHORIZED, f"Expected 401 for {method} {endpoint}"
