"""API contract extractor — reads OpenAPI, Swagger, GraphQL schema files."""
from pathlib import Path
from typing import List, Optional, Tuple

from .base import BaseGenerator
from ..utils.files import safe_read_text


class ContractsGenerator(BaseGenerator):
    """Extract API contracts from spec files present in the repository."""

    def __init__(self, root: Path, config: dict):
        super().__init__(root, config)

    @property
    def output_filename(self) -> str:
        return "api-contract.md"

    def generate(self) -> Tuple[str, List[Path]]:
        result = self._find_openapi()
        if result:
            return result

        result = self._find_graphql()
        if result:
            return result

        result = self._find_api_docs()
        if result:
            return result

        return "", []

    def _find_openapi(self) -> Optional[Tuple[str, List[Path]]]:
        for name in [
            "openapi.yaml", "openapi.yml", "openapi.json",
            "swagger.yaml", "swagger.yml", "swagger.json",
            "api-spec.yaml", "api-spec.yml",
        ]:
            path = self.root / name
            if path.exists():
                content = safe_read_text(path)
                if content:
                    ext = path.suffix.lstrip(".")
                    return f"# API Contract\n\n```{ext}\n{content}\n```", [path]
        return None

    def _find_graphql(self) -> Optional[Tuple[str, List[Path]]]:
        for name in ["schema.graphql", "schema.gql"]:
            path = self.root / name
            if path.exists():
                content = safe_read_text(path)
                if content:
                    return f"# GraphQL Schema\n\n```graphql\n{content}\n```", [path]
        return None

    def _find_api_docs(self) -> Optional[Tuple[str, List[Path]]]:
        for rel in ["API.md", "api/README.md", "docs/api.md"]:
            path = self.root / rel
            if path.exists():
                content = safe_read_text(path)
                if content:
                    return f"# API Documentation\n\n{content}", [path]
        return None
