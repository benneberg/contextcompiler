#!/usr/bin/env python3
"""
Tests for cross-repository conflict detection.
"""
import subprocess
import sys
import json
import shutil
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "llm-context-setup.py"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestConflictDetection:
    """Test conflict detection functionality."""
    
    @pytest.fixture
    def workspace_with_conflicts(self, tmp_path):
        """Create a workspace with intentional conflicts."""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        # Create workspace manifest
        manifest = """
name: test-platform
version: 1

services:
  service-a:
    path: ./service-a
    type: backend-api
    tags: [core]
    
  service-b:
    path: ./service-b
    type: backend-api
    tags: [core]
    depends_on: [service-a]
"""
        (workspace_dir / "ccc-workspace.yml").write_text(manifest)
        
        # Create service-a with Platform enum
        service_a = workspace_dir / "service-a" / "src"
        service_a.mkdir(parents=True)
        
        service_a_types = """
export enum Platform {
  ANDROID = "android",
  IOS = "ios",
}

export interface User {
  id: string;
  name: string;
  email: string;
}

export const API_VERSION = "v1";
export const MAX_RETRIES = 3;
"""
        (service_a / "types.ts").write_text(service_a_types)
        
        # Create package.json for service-a
        (workspace_dir / "service-a" / "package.json").write_text('{"name": "service-a"}')
        
        # Create service-b with DIFFERENT Platform enum (conflict!)
        service_b = workspace_dir / "service-b" / "src"
        service_b.mkdir(parents=True)
        
        service_b_types = """
export enum Platform {
  ANDROID = "android",
  IOS = "ios",
  WEB = "web",
}

export interface User {
  id: string;
  name: string;
  // Missing email field (conflict!)
  platform: Platform;
}

export const API_VERSION = "v2";
export const MAX_RETRIES = 3;
"""
        (service_b / "types.ts").write_text(service_b_types)
        
        # Create package.json for service-b
        (workspace_dir / "service-b" / "package.json").write_text('{"name": "service-b"}')
        
        return workspace_dir
    
    def test_detects_enum_mismatch(self, workspace_with_conflicts):
        """Test that enum mismatches are detected."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_conflicts,
            capture_output=True,
            text=True,
        )
        
        # Should find the Platform enum mismatch
        assert "Platform" in result.stdout or "enum" in result.stdout.lower()
        assert "mismatch" in result.stdout.lower() or "conflict" in result.stdout.lower()
    
    def test_detects_interface_mismatch(self, workspace_with_conflicts):
        """Test that interface mismatches are detected."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_conflicts,
            capture_output=True,
            text=True,
        )
        
        # Should find the User interface mismatch
        assert "User" in result.stdout or "interface" in result.stdout.lower()
    
    def test_detects_constant_mismatch(self, workspace_with_conflicts):
        """Test that constant mismatches are detected."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_conflicts,
            capture_output=True,
            text=True,
        )
        
        # Should find the API_VERSION constant mismatch
        assert "API_VERSION" in result.stdout or "constant" in result.stdout.lower()
    
    def test_generates_conflict_report(self, workspace_with_conflicts):
        """Test that conflict report is generated."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_conflicts,
            capture_output=True,
            text=True,
        )
        
        assert result.returncode in [0, 1]  # 1 if errors found
        
        # Check report was generated
        report_file = workspace_with_conflicts / "workspace-context" / "conflicts-report.md"
        assert report_file.exists(), "Conflict report not generated"
        
        report_content = report_file.read_text()
        assert "Conflict" in report_content or "conflict" in report_content
    
    def test_no_conflicts_when_consistent(self, tmp_path):
        """Test that no conflicts are reported for consistent services."""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        # Create workspace manifest
        manifest = """
name: consistent-platform
version: 1

services:
  service-a:
    path: ./service-a
    type: backend-api
    tags: [core]
"""
        (workspace_dir / "ccc-workspace.yml").write_text(manifest)
        
        # Create service-a with types
        service_a = workspace_dir / "service-a" / "src"
        service_a.mkdir(parents=True)
        
        (service_a / "types.ts").write_text("""
export interface UniqueType {
  id: string;
}
""")
        (workspace_dir / "service-a" / "package.json").write_text('{"name": "service-a"}')
        
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_dir,
            capture_output=True,
            text=True,
        )
        
        # Should find no conflicts
        assert "No conflicts" in result.stdout or "0" in result.stdout
    
    def test_workspace_doctor_alias(self, workspace_with_conflicts):
        """Test that 'workspace doctor' works as an alias for conflicts."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "doctor"],
            cwd=workspace_with_conflicts,
            capture_output=True,
            text=True,
        )
        
        # Should work the same as conflicts
        assert result.returncode in [0, 1]
        assert "Conflict" in result.stdout or "issue" in result.stdout.lower()


class TestConflictSeverity:
    """Test conflict severity levels."""
    
    @pytest.fixture
    def workspace_with_severity_levels(self, tmp_path):
        """Create workspace with different severity conflicts."""
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        
        manifest = """
name: test-severity
version: 1

services:
  svc-a:
    path: ./svc-a
    type: backend-api
    tags: [core]
  svc-b:
    path: ./svc-b
    type: backend-api
    tags: [core]
"""
        (workspace_dir / "ccc-workspace.yml").write_text(manifest)
        
        # Service A
        svc_a = workspace_dir / "svc-a" / "src"
        svc_a.mkdir(parents=True)
        (svc_a / "types.ts").write_text("""
// Error: Enum mismatch
export enum Status {
  ACTIVE = "active",
  INACTIVE = "inactive",
}

// Info: Naming inconsistency
export interface UserData {
  id: string;
}
""")
        (workspace_dir / "svc-a" / "package.json").write_text('{"name": "svc-a"}')
        
        # Service B
        svc_b = workspace_dir / "svc-b" / "src"
        svc_b.mkdir(parents=True)
        (svc_b / "types.ts").write_text("""
// Error: Different enum values
export enum Status {
  ACTIVE = "active",
  INACTIVE = "inactive",
  PENDING = "pending",
}

// Info: Different casing
export interface userData {
  id: string;
}
""")
        (workspace_dir / "svc-b" / "package.json").write_text('{"name": "svc-b"}')
        
        return workspace_dir
    
    def test_errors_cause_nonzero_exit(self, workspace_with_severity_levels):
        """Test that errors cause non-zero exit code."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_severity_levels,
            capture_output=True,
            text=True,
        )
        
        # Should exit with 1 because of enum mismatch error
        assert result.returncode == 1
    
    def test_shows_severity_counts(self, workspace_with_severity_levels):
        """Test that severity counts are shown."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "workspace", "conflicts"],
            cwd=workspace_with_severity_levels,
            capture_output=True,
            text=True,
        )
        
        # Should show error and warning/info counts
        assert "Error" in result.stdout or "error" in result.stdout
