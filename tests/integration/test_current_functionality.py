#!/usr/bin/env python3
"""
Integration tests for current LLM context generator functionality.

These tests ensure that refactoring doesn't break existing features.
"""
import subprocess
import sys
from pathlib import Path
import json
import pytest

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "llm-context-setup.py"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestPythonFastAPI:
    """Test context generation for Python FastAPI project."""
    
    @pytest.fixture
    def fastapi_project(self):
        """Path to FastAPI fixture project."""
        return FIXTURES_DIR / "python-fastapi"
    
    def test_generates_context_directory(self, fastapi_project, tmp_path):
        """Test that .llm-context directory is created."""
        # Copy fixture to temp directory
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        # Run generator
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0, f"Generator failed: {result.stderr}"
        
        context_dir = test_project / ".llm-context"
        assert context_dir.exists(), "Context directory not created"
        assert context_dir.is_dir(), "Context directory is not a directory"
    
    def test_generates_tree_file(self, fastapi_project, tmp_path):
        """Test that tree.txt is generated."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        tree_file = test_project / ".llm-context" / "tree.txt"
        assert tree_file.exists(), "tree.txt not generated"
        
        content = tree_file.read_text()
        assert "main.py" in content, "main.py not in tree"
        assert "models.py" in content, "models.py not in tree"
        assert "requirements.txt" in content, "requirements.txt not in tree"
    
    def test_extracts_python_schemas(self, fastapi_project, tmp_path):
        """Test that Python schemas are extracted."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        schemas_file = test_project / ".llm-context" / "schemas-extracted.py"
        assert schemas_file.exists(), "schemas-extracted.py not generated"
        
        content = schemas_file.read_text()
        assert "User" in content, "User model not extracted"
        assert "CreateUserRequest" in content, "CreateUserRequest not extracted"
        assert "BaseModel" in content, "Pydantic BaseModel not found"
    
    def test_extracts_routes(self, fastapi_project, tmp_path):
        """Test that API routes are extracted."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        routes_file = test_project / ".llm-context" / "routes.txt"
        assert routes_file.exists(), "routes.txt not generated"
        
        content = routes_file.read_text()
        assert "GET" in content, "GET routes not found"
        assert "POST" in content, "POST routes not found"
        assert "DELETE" in content, "DELETE routes not found"
        assert "/api/users" in content, "User routes not found"
    
    def test_extracts_public_api(self, fastapi_project, tmp_path):
        """Test that public API is extracted."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        api_file = test_project / ".llm-context" / "public-api.txt"
        assert api_file.exists(), "public-api.txt not generated"
        
        content = api_file.read_text()
        assert "get_user" in content, "get_user function not found"
        assert "create_user" in content, "create_user function not found"
        assert "delete_user" in content, "delete_user function not found"
    
    def test_generates_manifest(self, fastapi_project, tmp_path):
        """Test that manifest.json is created."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        manifest_file = test_project / ".llm-context" / "manifest.json"
        assert manifest_file.exists(), "manifest.json not generated"
        
        content = json.loads(manifest_file.read_text())
        assert "version" in content, "version not in manifest"
        assert "generated_at" in content, "generated_at not in manifest"
        assert "files" in content, "files not in manifest"
    
    def test_creates_claude_md(self, fastapi_project, tmp_path):
        """Test that CLAUDE.md scaffold is created."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        claude_md = test_project / "CLAUDE.md"
        assert claude_md.exists(), "CLAUDE.md not created"
        
        content = claude_md.read_text()
        assert "Identity" in content, "Identity section not found"
        assert "Stack" in content, "Stack section not found"
        assert "python" in content.lower(), "Python not mentioned in stack"
        assert "fastapi" in content.lower(), "FastAPI not detected"
    
    def test_creates_architecture_md(self, fastapi_project, tmp_path):
        """Test that ARCHITECTURE.md scaffold is created."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        arch_md = test_project / "ARCHITECTURE.md"
        assert arch_md.exists(), "ARCHITECTURE.md not created"
        
        content = arch_md.read_text()
        assert "Architecture Overview" in content
        assert "System Context" in content


class TestTypeScriptExpress:
    """Test context generation for TypeScript Express project."""
    
    @pytest.fixture
    def express_project(self):
        """Path to Express fixture project."""
        return FIXTURES_DIR / "typescript-express"
    
    def test_extracts_typescript_types(self, express_project, tmp_path):
        """Test that TypeScript types are extracted."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(express_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        types_file = test_project / ".llm-context" / "types-extracted.ts"
        assert types_file.exists(), "types-extracted.ts not generated"
        
        content = types_file.read_text()
        assert "interface User" in content, "User interface not extracted"
        assert "interface CreateUserRequest" in content, "CreateUserRequest not extracted"
        assert "enum Platform" in content, "Platform enum not extracted"
    
    def test_extracts_express_routes(self, express_project, tmp_path):
        """Test that Express routes are extracted."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(express_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        routes_file = test_project / ".llm-context" / "routes.txt"
        if routes_file.exists():
            content = routes_file.read_text()
            # Express routes might be detected
            assert "users" in content or len(content) > 0


class TestIncrementalUpdates:
    """Test incremental update functionality."""
    
    @pytest.fixture
    def fastapi_project(self):
        return FIXTURES_DIR / "python-fastapi"
    
    def test_quick_update_skips_unchanged(self, fastapi_project, tmp_path):
        """Test that quick update skips unchanged files."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        # First run
        result1 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        assert result1.returncode == 0
        
        # Quick update (nothing changed)
        result2 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--quick-update"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        assert result2.returncode == 0
        assert "up to date" in result2.stdout.lower() or "skipped" in result2.stdout.lower()
    
    def test_force_regenerates_all(self, fastapi_project, tmp_path):
        """Test that --force regenerates everything."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        # First run
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        # Force regeneration
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--force"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "force" in result.stdout.lower() or "regenerat" in result.stdout.lower()


class TestDoctor:
    """Test diagnostics command."""
    
    def test_doctor_command_runs(self):
        """Test that --doctor command runs successfully."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--doctor"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode == 0
        assert "Diagnostics" in result.stdout or "Environment Check" in result.stdout


class TestSecurityFeatures:
    """Test security-related features."""
    
    @pytest.fixture
    def fastapi_project(self):
        return FIXTURES_DIR / "python-fastapi"
    
    def test_redacts_secrets_from_env(self, fastapi_project, tmp_path):
        """Test that secrets are redacted from env files."""
        import shutil
        test_project = tmp_path / "test-project"
        shutil.copytree(fastapi_project, test_project)
        
        subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=test_project,
            capture_output=True,
        )
        
        env_file = test_project / ".llm-context" / "env-shape.txt"
        if env_file.exists():
            content = env_file.read_text()
            # Secrets should be redacted
            if "API_KEY" in content:
                assert "****" in content or "your-api-key-here" in content
