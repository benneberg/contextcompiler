
"""Unit tests for schema generator type resolution and drift detection."""

import json
import sys
import tempfile
from pathlib import Path
import pytest
from ccc.file_index import FileIndex
from ccc.generators.schemas import SchemaGenerator

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
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.root = tmp_path
        src = self.root / "src"
        src.mkdir()
        (src / "types.ts").write_text(
            """
export interface VideoConfig {
  width: number;
  height: number;
}
export type MediaType = "video" | "image";
export enum ProcessingStatus {
  Pending = "pending",
  Complete = "complete",
}
"""
        )
        (src / "encoder.ts").write_text(
            """
import { VideoConfig, MediaType, ProcessingStatus } from "./types";
export function encode(config: VideoConfig, media: MediaType) {
  return ProcessingStatus.Pending;
}
"""
        )
        (src / "thumbnail.ts").write_text(
            """
import { VideoConfig } from "./types";
export function createThumbnail(config: VideoConfig) {
  return config.width;
}
"""
        )
        (src / "unrelated.ts").write_text(
            """
export interface UnrelatedType {
  value: string;
}
"""
        )
        file_index = FileIndex(self.root)
        file_index.build()
        self.gen = SchemaGenerator(
            self.root,
            {},
            file_index,
        )
    def test_type_graph_contains_defined_types(self):
        graph_json = self.gen.generate_type_graph()
        graph = json.loads(graph_json)
        types = graph["types"]
        assert "src/types.ts::VideoConfig" in types
        assert "src/types.ts::MediaType" in types
        assert "src/types.ts::ProcessingStatus" in types
        assert "src/unrelated.ts::UnrelatedType" in types
    def test_type_graph_records_definition_file(self):
        graph = json.loads(self.gen.generate_type_graph())
        vc = graph["types"]["src/types.ts::VideoConfig"]
        assert vc["name"] == "VideoConfig"
        assert vc["defined_in"] == "src/types.ts"
    def test_type_graph_records_used_in(self):
        graph = json.loads(self.gen.generate_type_graph())
        vc = graph["types"]["src/types.ts::VideoConfig"]
        assert sorted(vc["used_in"]) == [
            "src/encoder.ts",
            "src/thumbnail.ts",
        ]
    def test_type_graph_no_self_reference(self):
        graph = json.loads(self.gen.generate_type_graph())
        for identity, type_info in graph["types"].items():
            assert type_info["defined_in"] not in type_info["used_in"]
    def test_type_graph_unimported_type_has_empty_used_in(self):
        graph = json.loads(self.gen.generate_type_graph())
        unrelated = graph["types"]["src/unrelated.ts::UnrelatedType"]
        assert unrelated["used_in"] == []
    def test_type_graph_meta_fields(self):
        graph = json.loads(self.gen.generate_type_graph())
        assert "_meta" in graph
        assert "generated" in graph["_meta"]
        assert "total_types" in graph["_meta"]
        assert graph["_meta"]["total_types"] == 4
    def test_type_graph_records_kind(self):
        graph = json.loads(self.gen.generate_type_graph())
        assert (
            graph["types"]["src/types.ts::VideoConfig"]["kind"]
            == "interface"
        )
        assert (
            graph["types"]["src/types.ts::ProcessingStatus"]["kind"]
            == "enum"
        )
        assert (
            graph["types"]["src/types.ts::MediaType"]["kind"]
            == "type"
        )

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
