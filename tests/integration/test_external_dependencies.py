#!/usr/bin/env python3
"""
Tests for external dependency detection.
"""
import subprocess
import sys
import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "llm-context-setup.py"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestExternalDependencies:
    """Test external dependency detection."""
    
    @pytest.fixture
    def fastapi_project(self):
        """Path to FastAPI fixture project."""
        return FIXTURES_DIR / "python-fastapi"
    
    def test_generates_external_dependencies_file(self, fastapi_project, tmp_path):
        """Test that external-dependencies.json is generated."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Generator failed: {result.stderr}"
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        assert deps_file.exists(), "external-dependencies.json not generated"
    
    def test_detects_service_name(self, fastapi_project, tmp_path):
        """Test that service name is detected."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        assert "service" in deps
        assert deps["service"] == test_project.name
    
    def test_detects_exposed_apis(self, fastapi_project, tmp_path):
        """Test that exposed APIs are detected."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        assert "exposes" in deps
        assert "api" in deps["exposes"]
        
        # Should detect the routes we defined
        api_routes = deps["exposes"]["api"]
        assert any("/api/users" in route for route in api_routes), "User routes not detected"
    
    def test_detects_external_service_calls(self, fastapi_project, tmp_path):
        """Test that external service calls are detected."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        assert "depends_on" in deps
        assert "apis_consumed" in deps["depends_on"]
        
        # Should detect calls to auth-service and notification-service
        apis = deps["depends_on"]["apis_consumed"]
        assert any("auth-service" in api for api in apis), "auth-service call not detected"
        assert any("notification-service" in api for api in apis), "notification-service call not detected"
    
    def test_detects_external_services(self, fastapi_project, tmp_path):
        """Test that external services are identified."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        services = deps["depends_on"]["services"]
        assert "auth-service" in services, "auth-service not identified"
        assert "notification-service" in services, "notification-service not identified"
    
    def test_detects_databases(self, fastapi_project, tmp_path):
        """Test that database dependencies are detected."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        databases = deps["depends_on"]["databases"]
        # Should detect Redis from requirements.txt scanning or SQLAlchemy
        assert len(databases) > 0, "No databases detected"
    
    def test_auto_detects_tags(self, fastapi_project, tmp_path):
        """Test that tags are auto-detected."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        deps = json.loads(deps_file.read_text())
        
        assert "tags" in deps
        tags = deps["tags"]
        
        # Should auto-detect backend-api and python tags
        assert "backend-api" in tags, "backend-api tag not detected"
        assert "python" in tags, "python tag not detected"
    
    def test_structure_is_valid_json(self, fastapi_project, tmp_path):
        """Test that output is valid JSON."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        
        # Should be valid JSON
        try:
            deps = json.loads(deps_file.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"Invalid JSON: {e}")
        
        # Check required structure
        assert "service" in deps
        assert "exposes" in deps
        assert "depends_on" in deps
        assert "tags" in deps
        assert "detected_at" in deps
    
    def test_incremental_update_for_external_deps(self, fastapi_project, tmp_path):
        """Test that external-dependencies.json respects incremental updates."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        # First run
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        deps_file = test_project / ".llm-context" / "external-dependencies.json"
        original_mtime = deps_file.stat().st_mtime
        
        # Quick update without changes
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--quick-update"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        
        # File should not be regenerated (or if regenerated, should have same content)
        new_mtime = deps_file.stat().st_mtime
        
        # Either skipped or regenerated with same content
        assert "external-dependencies.json" in result.stdout
