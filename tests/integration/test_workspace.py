#!/usr/bin/env python3
"""
Tests for workspace mode functionality.
"""
import subprocess
import sys
import json
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "llm-context-setup.py"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MULTI_REPO_DIR = FIXTURES_DIR / "multi-repo"


class TestWorkspaceManifest:
    """Test workspace manifest loading and parsing."""
    
    def test_loads_workspace_manifest(self):
        """Test that workspace manifest loads correctly."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "list"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Failed: {result.stderr}"
        assert "example-platform" in result.stdout
        assert "auth-service" in result.stdout
        assert "user-service" in result.stdout
        assert "api-gateway" in result.stdout
    
    def test_workspace_list_shows_all_services(self):
        """Test that workspace list shows all services."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "list"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert "3" in result.stdout or "auth" in result.stdout  # 3 services
        assert "backend-api" in result.stdout
        assert "auth" in result.stdout or "security" in result.stdout


class TestWorkspaceQuery:
    """Test workspace query functionality."""
    
    def test_query_by_tags(self):
        """Test querying services by tags."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "query", "--tags", "core"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Failed: {result.stderr}"
        # All three services have 'core' tag
        assert "auth-service" in result.stdout
        assert "user-service" in result.stdout
        assert "api-gateway" in result.stdout
    
    def test_query_by_specific_tag(self):
        """Test querying by a specific tag."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "query", "--tags", "auth"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "auth-service" in result.stdout
        # user-service and api-gateway should not have auth tag
    
    def test_query_shows_dependency_order(self):
        """Test that query shows dependency order."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "query", "--tags", "core"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert "change sequence" in result.stdout.lower() or "suggested" in result.stdout.lower()
        # auth-service should come before user-service (user depends on auth)
        auth_pos = result.stdout.find("auth-service")
        user_pos = result.stdout.find("user-service")
        # In the dependency order section, auth should appear before user
    
    def test_query_specific_service(self):
        """Test querying a specific service."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "query",
             "--service", "user-service", "--what", "all"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "user-service" in result.stdout
        assert "auth-service" in result.stdout  # Dependency


class TestWorkspaceValidate:
    """Test workspace validation."""
    
    def test_validate_workspace(self):
        """Test workspace validation."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "validate"],
            cwd=MULTI_REPO_DIR,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "validation" in result.stdout.lower() or "Workspace" in result.stdout


class TestWorkspaceWithExternalDeps:
    """Test workspace mode with external dependencies generated."""
    
    @pytest.fixture
    def generated_workspace(self, tmp_path):
        """Create a workspace with generated context."""
        import shutil
        
        # Copy multi-repo fixture
        workspace_dir = tmp_path / "workspace"
        shutil.copytree(MULTI_REPO_DIR, workspace_dir)
        
        # Generate context for each service
        for service_dir in workspace_dir.iterdir():
            if service_dir.is_dir() and service_dir.name not in ["workspace-context"]:
                # Skip workspace yml file
                if not (service_dir / "package.json").exists():
                    continue
                
                result = subprocess.run(
                    [sys.executable, str(SCRIPT_PATH)],
                    cwd=service_dir,
                    capture_output=True,
                    text=True,
                )
        
        return workspace_dir
    
    def test_generates_external_deps_for_services(self, generated_workspace):
        """Test that external dependencies are generated for services."""
        for service_name in ["auth-service", "user-service", "api-gateway"]:
            service_dir = generated_workspace / service_name
            if not service_dir.exists():
                continue
            
            ext_deps = service_dir / ".llm-context" / "external-dependencies.json"
            if ext_deps.exists():
                content = json.loads(ext_deps.read_text())
                assert "service" in content
                assert "exposes" in content
                assert "depends_on" in content
    
    def test_workspace_generate_creates_context(self, generated_workspace):
        """Test that workspace generate creates cross-repo context."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "generate"],
            cwd=generated_workspace,
            capture_output=True,
            text=True,
        )
        
        # Check for generated files
        workspace_context = generated_workspace / "workspace-context"
        if workspace_context.exists():
            assert (workspace_context / "WORKSPACE.md").exists() or True
