"""
Module summary generator — uses an LLM to summarise each source module.

Requires either:
  pip install anthropic   (for provider: anthropic)
  pip install openai      (for provider: openai)

Enabled via config:
  generate:
    module_summaries: true
  llm_summaries:
    provider: anthropic
    model: claude-haiku-4-5-20251001
    max_modules: 30
    min_file_size_bytes: 300
"""
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text, should_skip_path


class ModuleSummaryGenerator(BaseGenerator):
    """Generate LLM-powered per-module summaries."""

    def __init__(self, root: Path, config: dict, file_index: FileIndex):
        super().__init__(root, config)
        self.index = file_index
        self._client = None

    @property
    def output_filename(self) -> str:
        return "module-index.md"

    def generate(self) -> Tuple[str, List[Path]]:
        """Generate the module index file (list of all summaries)."""
        results = self.generate_all()
        if not results:
            return "", []

        lines = ["# Module Summaries Index", ""]
        source_files: List[Path] = []
        for filename, (_, files) in sorted(results.items()):
            lines.append(f"- [{filename}](modules/{filename})")
            source_files.extend(files)

        return "\n".join(lines), source_files

    def generate_all(self) -> Dict[str, Tuple[str, List[Path]]]:
        """Generate summaries for all qualifying modules. Returns {filename: (content, sources)}."""
        client = self._get_client()
        if not client:
            return {}

        cfg = self.config.get("llm_summaries", {})
        min_size = cfg.get("min_file_size_bytes", 300)
        max_modules = cfg.get("max_modules", 30)
        langs = self.index.detect_languages()

        # Collect candidate files across all detected languages
        lang_exts = {
            "python": ".py", "typescript": ".ts", "javascript": ".js",
            "rust": ".rs", "go": ".go", "csharp": ".cs",
        }
        candidates: List[Path] = []
        for lang in langs:
            ext = lang_exts.get(lang)
            if not ext:
                continue
            for fi in self.index.by_extension(ext):
                if min_size < fi.size < 100_000:
                    candidates.append(fi.path)

        # Prioritise largest files (most content)
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        candidates = candidates[:max_modules]

        if not candidates:
            return {}

        results: Dict[str, Tuple[str, List[Path]]] = {}
        total = len(candidates)
        print(f"   Summarising {total} module(s)...")

        for i, filepath in enumerate(candidates, 1):
            try:
                rel = filepath.relative_to(self.root)
                source = safe_read_text(filepath)
                if not source:
                    continue
                if len(source) > 20_000:
                    source = source[:20_000] + "\n\n# [TRUNCATED]"

                print(f"   [{i}/{total}] {rel}", end="\r", flush=True)
                summary = self._call_llm(client, str(rel), source)
                if summary:
                    key = str(rel).replace("/", "__").replace("\\", "__")
                    key = re.sub(r"\.\w+$", ".md", key)
                    content = f"# Module: {rel}\n\n{summary}\n"
                    results[key] = (content, [filepath])
            except Exception as exc:
                print(f"\n   Warning: could not summarise {filepath.name}: {exc}")

        print()  # newline after \r progress
        return results

    # ── LLM client ────────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client:
            return self._client

        provider = self.config.get("llm_summaries", {}).get("provider", "anthropic")

        if provider == "anthropic":
            try:
                from anthropic import Anthropic
                self._client = Anthropic()
            except ImportError:
                print("   Warning: pip install anthropic  (needed for module summaries)")
                return None
        elif provider == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except ImportError:
                print("   Warning: pip install openai  (needed for module summaries)")
                return None
        else:
            print(f"   Warning: unknown llm_summaries.provider '{provider}'")
            return None

        return self._client

    def _call_llm(self, client, filepath: str, source: str) -> Optional[str]:
        cfg = self.config.get("llm_summaries", {})
        provider = cfg.get("provider", "anthropic")
        model = cfg.get("model", "claude-haiku-4-5-20251001")

        prompt = f"""Analyse this source module and produce a concise technical summary.

File: {filepath}

Source:
{source}

Provide exactly these sections:
1. **Purpose** — one sentence.
2. **Public Interface** — key classes/functions with brief descriptions.
3. **Dependencies** — internal imports and external packages used.
4. **Key Patterns** — design patterns, important invariants, or gotchas.
5. **Data Flow** — how data enters and exits this module.

Be precise and concise. No preamble."""

        try:
            if provider == "anthropic":
                response = client.messages.create(
                    model=model,
                    max_tokens=1200,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text

            elif provider == "openai":
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=1200,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.choices[0].message.content

        except Exception as exc:
            print(f"\n   LLM error for {filepath}: {exc}")
            return None

        return None
