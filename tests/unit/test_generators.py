
"""Unit tests for schema generator type resolution and drift detection."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

TYPES_TS = """\
export interface VideoConfig {
  codec: string;
  bitrate: number;
}

export type MediaType = "video" | "image" | "audio";

export enum ProcessingStatus {
  Pending = "pending",
  Done = "done",
}
"""

ENCODER_TS = """\
import { VideoConfig, MediaType } from './types';
import { ProcessingStatus } from './types';

export function encode(config: VideoConfig): void {
  console.log(config);
}
"""

THUMBNAIL_TS = """\
import { VideoConfig } from './types';

export function generateThumbnail(config: VideoConfig): string {
  return 'thumb.jpg';
}
"""

UNRELATED_TS = """\
export interface UnrelatedType {
  x: number;
}
"""


def make_ts_project(tmp_path: Path) -> Path:
    """Create a minimal TypeScript project for testing."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "types.ts").write_text(TYPES_TS)
    (src / "encoder.ts").write_text(ENCODER_TS)
    (src / "thumbnail.ts").write_text(THUMBNAIL_TS)
    (src / "unrelated.ts").write_text(UNRELATED_TS)
    return tmp_path


# ── Type graph tests ──────────────────────────────────────────────────────────

class TestTypeGraphGeneration:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        make_ts_project(self.root)

        from ccc.file_index import FileIndex, EXCLUDE_DIRS
        self.file_index = FileIndex(self.root, EXCLUDE_DIRS).build()

        from ccc.generators.schemas import SchemaGenerator
        self.gen = SchemaGenerator(self.root, {}, self.file_index)

    def test_type_graph_contains_defined_types(self):
        graph_json = self.gen.generate_type_graph()
        graph = json.loads(graph_json)
        types = graph["types"]
        assert "VideoConfig" in types
        assert "MediaType" in types
        assert "ProcessingStatus" in types

    def test_type_graph_records_definition_file(self):
        graph = json.loads(self.gen.generate_type_graph())
        vc = graph["types"]["VideoConfig"]
        assert "types.ts" in vc["defined_in"]

    def test_type_graph_records_used_in(self):
        graph = json.loads(self.gen.generate_type_graph())
        vc = graph["types"]["VideoConfig"]
        used = vc["used_in"]
        # Both encoder.ts and thumbnail.ts import VideoConfig
        assert any("encoder.ts" in u for u in used)
        assert any("thumbnail.ts" in u for u in used)

    def test_type_graph_no_self_reference(self):
        graph = json.loads(self.gen.generate_type_graph())
        for name, info in graph["types"].items():
            assert info["defined_in"] not in info["used_in"], (
                f"{name} should not list its own file in used_in"
            )

    def test_type_graph_unimported_type_has_empty_used_in(self):
        graph = json.loads(self.gen.generate_type_graph())
        # UnrelatedType is not imported by anyone
        ut = graph["types"].get("UnrelatedType")
        if ut:
            assert ut["used_in"] == []

    def test_type_graph_meta_fields(self):
        graph = json.loads(self.gen.generate_type_graph())
        assert "_meta" in graph
        assert "total_types" in graph["_meta"]
        assert graph["_meta"]["total_types"] > 0

    def test_type_graph_records_kind(self):
        graph = json.loads(self.gen.generate_type_graph())
        assert graph["types"]["VideoConfig"]["kind"] == "interface"
        assert graph["types"]["MediaType"]["kind"] == "type"
        assert graph["types"]["ProcessingStatus"]["kind"] == "enum"


# ── TypeScript extraction with used_in annotations ───────────────────────────

class TestTypeScriptExtractionAnnotations:

    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)
        make_ts_project(self.root)

        from ccc.file_index import FileIndex, EXCLUDE_DIRS
        fi = FileIndex(self.root, EXCLUDE_DIRS).build()
        from ccc.generators.schemas import SchemaGenerator
        self.gen = SchemaGenerator(self.root, {}, fi)

    def test_extracted_types_contains_used_in_annotation(self):
        results = self.gen.generate_all()
        if "types-extracted.ts" not in results:
            pytest.skip("No TypeScript files found")
        content, _ = results["types-extracted.ts"]
        # VideoConfig is imported by encoder and thumbnail
        assert "used in:" in content

    def test_extracted_types_lists_importing_files(self):
        results = self.gen.generate_all()
        if "types-extracted.ts" not in results:
            pytest.skip("No TypeScript files found")
        content, _ = results["types-extracted.ts"]
        assert "encoder.ts" in content or "thumbnail.ts" in content
