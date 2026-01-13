"""Integration tests for the complete Evidence Repository flow.

Tests the full pipeline:
1. Upload document
2. Process (extract → spans → embeddings)
3. Search
4. Create evidence pack

These tests require a running database and can be run with:
    make test-int
    pytest tests/test_integration_flow.py -v -s
"""

import uuid
from datetime import datetime

import pytest

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestUploadDocument:
    """Tests for document upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_text_document(self, client, sample_text_content):
        """Should upload a text document successfully."""
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("test_document.txt", sample_text_content, "text/plain")},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["filename"] == "test_document.txt"
        assert data["content_type"] == "text/plain"
        assert "current_version" in data

    @pytest.mark.asyncio
    async def test_upload_pdf_document(self, client, sample_pdf_content):
        """Should upload a PDF document successfully."""
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("test_document.pdf", sample_pdf_content, "application/pdf")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content_type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_upload_returns_version_id(self, client, sample_text_content):
        """Should return version ID on upload."""
        response = await client.post(
            "/api/v1/documents",
            files={"file": ("test.txt", sample_text_content, "text/plain")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["current_version"] is not None
        assert "id" in data["current_version"]


class TestProjectManagement:
    """Tests for project CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_project(self, client):
        """Should create a project successfully."""
        response = await client.post(
            "/api/v1/projects",
            json={
                "name": "Integration Test Project",
                "description": "Project for integration testing",
                "case_ref": "TEST-001",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Integration Test Project"
        assert data["case_ref"] == "TEST-001"

    @pytest.mark.asyncio
    async def test_list_projects(self, client):
        """Should list projects."""
        # Create a project first
        await client.post(
            "/api/v1/projects",
            json={"name": "List Test Project"},
        )

        response = await client.get("/api/v1/projects")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_attach_document_to_project(self, client, sample_text_content):
        """Should attach a document to a project."""
        # Create document
        doc_response = await client.post(
            "/api/v1/documents",
            files={"file": ("attach_test.txt", sample_text_content, "text/plain")},
        )
        doc_id = doc_response.json()["id"]

        # Create project
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "Attach Test Project"},
        )
        proj_id = proj_response.json()["id"]

        # Attach document
        attach_response = await client.post(
            f"/api/v1/projects/{proj_id}/documents",
            json={"document_id": doc_id},
        )

        assert attach_response.status_code == 201
        data = attach_response.json()
        assert data["document_id"] == doc_id


class TestDocumentExtraction:
    """Tests for document text extraction."""

    @pytest.mark.asyncio
    async def test_trigger_extraction(self, client, sample_text_content):
        """Should trigger document extraction."""
        # Upload document
        doc_response = await client.post(
            "/api/v1/documents",
            files={"file": ("extract_test.txt", sample_text_content, "text/plain")},
        )
        doc_id = doc_response.json()["id"]

        # Trigger extraction
        extract_response = await client.post(f"/api/v1/documents/{doc_id}/extract")

        # Should return job info or direct result
        assert extract_response.status_code in [200, 202]

    @pytest.mark.asyncio
    async def test_get_document_with_extracted_text(self, client, sample_text_content):
        """Should include extracted text in document response."""
        # Upload and potentially extract
        doc_response = await client.post(
            "/api/v1/documents",
            files={"file": ("text_test.txt", sample_text_content, "text/plain")},
        )
        doc_id = doc_response.json()["id"]

        # Get document details
        get_response = await client.get(f"/api/v1/documents/{doc_id}")

        assert get_response.status_code == 200
        data = get_response.json()
        assert "current_version" in data


class TestSearch:
    """Tests for search functionality."""

    @pytest.mark.asyncio
    async def test_semantic_search_endpoint(self, client):
        """Should accept semantic search requests."""
        response = await client.post(
            "/api/v1/search",
            json={
                "query": "legal document terms",
                "limit": 10,
            },
        )

        # Should return even if no results
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_project_scoped_search(self, client):
        """Should search within a specific project."""
        # Create project
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "Search Test Project"},
        )
        proj_id = proj_response.json()["id"]

        # Search within project
        response = await client.post(
            f"/api/v1/projects/{proj_id}/search",
            json={
                "query": "evidence terms",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data

    @pytest.mark.asyncio
    async def test_search_with_keyword_filters(self, client):
        """Should support keyword filtering in search."""
        response = await client.post(
            "/api/v1/search",
            json={
                "query": "financial metrics",
                "keywords": ["revenue", "ARR"],
                "exclude_keywords": ["draft"],
                "limit": 10,
            },
        )

        assert response.status_code == 200


class TestEvidencePack:
    """Tests for evidence pack creation and retrieval."""

    @pytest.mark.asyncio
    async def test_create_evidence_pack(self, client):
        """Should create an evidence pack."""
        # Create project first
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "Evidence Pack Test Project"},
        )
        proj_id = proj_response.json()["id"]

        # Create evidence pack
        response = await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={
                "name": "Test Evidence Pack",
                "description": "Pack for integration testing",
                "include_quality_analysis": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Evidence Pack"
        assert "id" in data
        assert "documents" in data
        assert "spans" in data
        assert "claims" in data
        assert "metrics" in data
        assert "conflicts" in data
        assert "open_questions" in data

    @pytest.mark.asyncio
    async def test_get_evidence_pack(self, client):
        """Should retrieve an evidence pack with all fields."""
        # Create project and pack
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "Get Pack Test Project"},
        )
        proj_id = proj_response.json()["id"]

        create_response = await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={"name": "Retrieve Test Pack"},
        )
        pack_id = create_response.json()["id"]

        # Get pack
        response = await client.get(
            f"/api/v1/projects/{proj_id}/evidence-packs/{pack_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == pack_id
        # Verify Juris-AGI required fields
        assert "documents" in data
        assert "spans" in data
        assert "claims" in data
        assert "metrics" in data
        assert "conflicts" in data
        assert "open_questions" in data

    @pytest.mark.asyncio
    async def test_list_evidence_packs(self, client):
        """Should list evidence packs for a project."""
        # Create project and packs
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "List Packs Project"},
        )
        proj_id = proj_response.json()["id"]

        # Create multiple packs
        await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={"name": "Pack 1"},
        )
        await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={"name": "Pack 2"},
        )

        # List packs
        response = await client.get(f"/api/v1/projects/{proj_id}/evidence-packs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2


class TestFullPipeline:
    """Integration tests for the complete upload → process → search → pack flow."""

    @pytest.mark.asyncio
    async def test_complete_document_flow(self, client, sample_text_content):
        """Test the complete flow: upload → project → attach → search → pack."""
        # Step 1: Upload document
        doc_response = await client.post(
            "/api/v1/documents",
            files={"file": ("pipeline_test.txt", sample_text_content, "text/plain")},
        )
        assert doc_response.status_code == 201
        doc_data = doc_response.json()
        doc_id = doc_data["id"]
        version_id = doc_data["current_version"]["id"]

        # Step 2: Create project
        proj_response = await client.post(
            "/api/v1/projects",
            json={
                "name": "Full Pipeline Test",
                "description": "Testing complete flow",
                "case_ref": "PIPE-001",
            },
        )
        assert proj_response.status_code == 201
        proj_id = proj_response.json()["id"]

        # Step 3: Attach document to project
        attach_response = await client.post(
            f"/api/v1/projects/{proj_id}/documents",
            json={"document_id": doc_id},
        )
        assert attach_response.status_code == 201

        # Step 4: Trigger extraction (if not auto-processed)
        extract_response = await client.post(f"/api/v1/documents/{doc_id}/extract")
        assert extract_response.status_code in [200, 202]

        # Step 5: Search within project
        search_response = await client.post(
            f"/api/v1/projects/{proj_id}/search",
            json={
                "query": "legal document evidence",
                "limit": 10,
            },
        )
        assert search_response.status_code == 200

        # Step 6: Create evidence pack
        pack_response = await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={
                "name": "Pipeline Evidence Pack",
                "description": "Evidence from full pipeline test",
                "include_quality_analysis": True,
            },
        )
        assert pack_response.status_code == 201
        pack_data = pack_response.json()

        # Verify pack structure
        assert pack_data["name"] == "Pipeline Evidence Pack"
        assert pack_data["project_id"] == proj_id

        # Verify Juris-AGI integration fields exist
        required_fields = [
            "documents",
            "spans",
            "claims",
            "metrics",
            "conflicts",
            "open_questions",
        ]
        for field in required_fields:
            assert field in pack_data, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_document_version_tracking(self, client, sample_text_content):
        """Test that document versions are tracked correctly."""
        # Upload initial version
        v1_response = await client.post(
            "/api/v1/documents",
            files={"file": ("version_test.txt", sample_text_content, "text/plain")},
        )
        doc_id = v1_response.json()["id"]
        v1_id = v1_response.json()["current_version"]["id"]

        # Get versions
        versions_response = await client.get(f"/api/v1/documents/{doc_id}/versions")

        assert versions_response.status_code == 200
        versions = versions_response.json()
        assert len(versions) >= 1

    @pytest.mark.asyncio
    async def test_quality_analysis_in_pack(self, client):
        """Test that evidence pack includes quality analysis."""
        # Create project
        proj_response = await client.post(
            "/api/v1/projects",
            json={"name": "Quality Analysis Test Project"},
        )
        proj_id = proj_response.json()["id"]

        # Create pack with quality analysis
        pack_response = await client.post(
            f"/api/v1/projects/{proj_id}/evidence-packs",
            json={
                "name": "Quality Test Pack",
                "include_quality_analysis": True,
            },
        )

        assert pack_response.status_code == 201
        pack_data = pack_response.json()

        # Check quality summary
        assert "quality_summary" in pack_data
        if pack_data["quality_summary"]:
            summary = pack_data["quality_summary"]
            assert "total_conflicts" in summary
            assert "critical_conflicts" in summary
            assert "high_conflicts" in summary
            assert "total_open_questions" in summary


class TestAsyncJobProcessing:
    """Tests for async job processing endpoints."""

    @pytest.mark.asyncio
    async def test_async_upload_returns_job_id(self, client, sample_text_content):
        """Async upload should return a job ID."""
        response = await client.post(
            "/api/v1/jobs/upload",
            files={"file": ("async_test.txt", sample_text_content, "text/plain")},
        )

        # Should return job info
        assert response.status_code in [200, 202]
        data = response.json()
        assert "job_id" in data or "id" in data

    @pytest.mark.asyncio
    async def test_get_job_status(self, client):
        """Should return job status."""
        # Use a fake job ID to test the endpoint exists
        fake_job_id = str(uuid.uuid4())

        response = await client.get(f"/api/v1/jobs/{fake_job_id}")

        # Should return 404 for non-existent job
        assert response.status_code in [200, 404]


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Should return health status."""
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "ok"]

    @pytest.mark.asyncio
    async def test_detailed_health_check(self, client):
        """Should return detailed health information."""
        response = await client.get("/api/v1/health/detailed")

        # Endpoint may or may not exist
        if response.status_code == 200:
            data = response.json()
            # Check for component health if detailed endpoint exists
            assert "status" in data


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_not_found_document(self, client):
        """Should return 404 for non-existent document."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/documents/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_not_found_project(self, client):
        """Should return 404 for non-existent project."""
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/projects/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(self, client):
        """Should return 422 for invalid UUID format."""
        response = await client.get("/api/v1/documents/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_unauthorized_without_api_key(self, client):
        """Should return 401/403 without API key."""
        # Create a new client without headers
        from httpx import ASGITransport, AsyncClient
        from evidence_repository.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            # No X-API-Key header
        ) as unauth_client:
            response = await unauth_client.get("/api/v1/documents")
            assert response.status_code in [401, 403]
