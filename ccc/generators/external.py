"""
External dependency detector.

Analyses source code to produce external-dependencies.json describing:
  - what API routes, events, and types this service exposes
  - what external APIs, databases, queues, and services it consumes
  - auto-detected tags (backend-api, frontend, database, etc.)

Works with Python, TypeScript/JavaScript, Rust, and Go.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .base import BaseGenerator
from ..file_index import FileIndex
from ..utils.files import safe_read_text, should_skip_path
from ..utils.formatting import get_timestamp


class ExternalDependencyGenerator(BaseGenerator):
    """Detect what a service exposes and what it depends on externally."""

    def __init__(
        self,
        root: Path,
        config: dict,
        file_index: FileIndex,
        languages: List[str],
        framework: str = "",
    ):
        super().__init__(root, config)
        self.index = file_index
        self.languages = languages
        self.framework = framework

    @property
    def output_filename(self) -> str:
        return "external-dependencies.json"

    def generate(self) -> Tuple[str, List[Path]]:
        deps = self.detect()
        return json.dumps(deps, indent=2), []

    def detect(self) -> dict:
        deps: Dict = {
            "service": self.root.name,
            "repository": self._get_repo_url(),
            "exposes": {"api": [], "events": [], "types": []},
            "depends_on": {
                "services": set(),
                "apis_consumed": [],
                "databases": [],
                "message_queues": [],
                "external_apis": [],
            },
            "tags": self._auto_detect_tags(),
            "detected_at": get_timestamp(),
        }

        if "python" in self.languages:
            self._detect_python(deps)
        if "typescript" in self.languages or "javascript" in self.languages:
            self._detect_js(deps)
        if "rust" in self.languages:
            self._detect_rust(deps)
        if "go" in self.languages:
            self._detect_go(deps)

        # Serialise sets → sorted lists, deduplicate
        deps["depends_on"]["services"] = sorted(deps["depends_on"]["services"])
        for key in ("api", "events", "types"):
            deps["exposes"][key] = sorted(set(deps["exposes"][key]))
        for key in deps["depends_on"]:
            if isinstance(deps["depends_on"][key], list):
                deps["depends_on"][key] = sorted(set(deps["depends_on"][key]))

        return deps

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_repo_url(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=self.root, capture_output=True, text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _auto_detect_tags(self) -> List[str]:
        tags: Set[str] = set()
        fw = self.framework.lower()
        if any(x in fw for x in ("fastapi", "flask", "django")):
            tags.add("backend-api")
        if any(x in fw for x in ("express", "nestjs")):
            tags.add("backend-api")
        if any(x in fw for x in ("react", "vue", "angular")):
            tags.add("frontend")
        if "nextjs" in fw:
            tags.update(("frontend", "ssr"))
        dir_tag_map = {
            "api": "api", "routes": "api",
            "models": "data", "schemas": "data",
            "services": "services",
            "components": "ui",
            "workers": "background-jobs", "tasks": "background-jobs",
            "migrations": "database",
        }
        for dirname, tag in dir_tag_map.items():
            if (self.root / dirname).exists() or (self.root / "src" / dirname).exists():
                tags.add(tag)
        tags.update(self.languages)
        return sorted(tags)

    # ── Python ────────────────────────────────────────────────────────────────

    def _detect_python(self, deps: dict) -> None:
        http_patterns = [
            (r'requests\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', 2),
            (r'httpx\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', 2),
            (r'aiohttp\.ClientSession\(\)\.(?:get|post|put|delete)\s*\(\s*["\']([^"\']+)', 1),
        ]
        db_patterns = [
            (r'psycopg2', "PostgreSQL"), (r'pymongo', "MongoDB"),
            (r'redis', "Redis"), (r'motor', "MongoDB"),
            (r'sqlalchemy.*postgresql', "PostgreSQL"),
            (r'sqlalchemy.*mysql', "MySQL"),
        ]
        mq_patterns = [
            (r'kafka', "Kafka"), (r'celery', "Celery/Redis"),
            (r'pika', "RabbitMQ"), (r'boto3.*sqs', "AWS SQS"),
        ]
        ext_api_patterns = [
            (r'STRIPE_', "Stripe"), (r'TWILIO_', "Twilio"),
            (r'SENDGRID_', "SendGrid"), (r'AWS_', "AWS"),
            (r'GOOGLE_CLOUD_', "Google Cloud"), (r'AZURE_', "Azure"),
        ]
        route_pattern = re.compile(
            r'@(?:app|router|api)\.(get|post|put|delete|patch|websocket)'
            r'\s*\(\s*["\']([^"\']+)["\']'
        )

        for fi in self.index.by_extension(".py"):
            content = safe_read_text(fi.path)
            if not content:
                continue

            # Exposed routes
            for method, path in route_pattern.findall(content):
                deps["exposes"]["api"].append(f"{method.upper()} {path}")

            # HTTP calls out
            for pattern, n_groups in http_patterns:
                for m in re.finditer(pattern, content):
                    url = m.group(n_groups)
                    method = m.group(1).upper() if n_groups == 2 else "GET"
                    if url.startswith("http"):
                        deps["depends_on"]["apis_consumed"].append(f"{method} {url}")
                        sm = re.search(r'https?://([^/:]+)', url)
                        if sm and sm.group(1) not in ("localhost", "127.0.0.1"):
                            deps["depends_on"]["services"].add(sm.group(1))

            # Databases
            for pattern, name in db_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    deps["depends_on"]["databases"].append(name)

            # Message queues
            for pattern, name in mq_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    deps["depends_on"]["message_queues"].append(name)

            # Events emitted
            for m in re.finditer(r'\.emit\s*\(\s*["\']([^"\']+)', content):
                deps["exposes"]["events"].append(m.group(1))

            # External API key patterns
            for pattern, svc in ext_api_patterns:
                if re.search(pattern, content):
                    deps["depends_on"]["external_apis"].append(svc)

    # ── JavaScript / TypeScript ───────────────────────────────────────────────

    def _detect_js(self, deps: dict) -> None:
        # HTTP clients
        http_patterns = [
            (r'fetch\s*\(\s*[`"\'](https?://[^`"\']+)', "GET", 1),
            (r'axios\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[`"\'](https?://[^`"\']+)', None, 2),
            (r'axios\.create\s*\(\s*\{[^}]*baseURL\s*:\s*[`"\'](https?://[^`"\']+)', "BASE", 1),
            (r'got\s*\.\s*(get|post|put|delete|patch)\s*\(\s*[`"\'](https?://[^`"\']+)', None, 2),
        ]

        # Exposed route patterns
        route_patterns = [
            # Express/fastify
            (r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*[`"\'](/[^`"\']+)', "express"),
            # NestJS
            (r'@(Get|Post|Put|Delete|Patch)\s*\(\s*[`"\'"]?([^`"\'")]+)', "nestjs"),
            # Next.js handlers
            (r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH)\s*\(', "nextjs"),
        ]

        db_patterns = [
            (r'@prisma/client|new\s+PrismaClient', "Database (Prisma)"),
            (r'@Entity\s*\(|getRepository', "Database (TypeORM)"),
            (r'drizzle\s*\(|from\s+["\']drizzle-orm', "Database (Drizzle)"),
            (r'mongoose\.connect|new\s+Schema\s*\(', "MongoDB"),
            (r'pg\.Pool|new\s+Pool\s*\(', "PostgreSQL"),
            (r'import.*from\s+["\']redis["\']|createClient.*redis', "Redis"),
            (r'import.*from\s+["\']ioredis["\']|new\s+Redis\s*\(', "Redis"),
            (r'mysql2|mysql\.createConnection', "MySQL"),
        ]

        mq_patterns = [
            (r'kafkajs|KafkaJS|new\s+Kafka\s*\(', "Kafka"),
            (r'amqplib|amqp\.connect', "RabbitMQ"),
            (r'new\s+Queue\s*\(|import.*from\s+["\']bullmq["\']', "Bull/BullMQ"),
            (r'SQSClient|@aws-sdk/client-sqs', "AWS SQS"),
        ]

        sdk_patterns = [
            (r'stripe|Stripe\s*\(', "Stripe"),
            (r'@auth0|Auth0Client|useClerk|ClerkProvider', "Auth"),
            (r'next-auth|NextAuth', "NextAuth"),
            (r'@supabase|createClient.*supabase', "Supabase"),
            (r'firebase|initializeApp', "Firebase"),
            (r'twilio|Twilio\s*\(', "Twilio"),
            (r'@sendgrid|sendgrid', "SendGrid"),
            (r'@aws-sdk/client-s3|S3Client', "AWS S3"),
            (r'@sentry|Sentry\.init', "Sentry"),
            (r'openai|OpenAI\s*\(', "OpenAI"),
            (r'@anthropic|Anthropic\s*\(', "Anthropic"),
            (r'algolia|algoliasearch', "Algolia"),
        ]

        file_exts = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

        for fi in self.index.by_extension(*file_exts):
            content = safe_read_text(fi.path)
            if not content:
                continue

            # HTTP calls out
            for pattern, default_method, group in http_patterns:
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    url = m.group(group)
                    method = (m.group(1).upper() if default_method is None and len(m.groups()) >= 1 else default_method) or "GET"
                    deps["depends_on"]["apis_consumed"].append(f"{method} {url}")
                    sm = re.search(r'https?://([^/:]+)', url)
                    if sm and sm.group(1) not in ("localhost", "127.0.0.1", "0.0.0.0"):
                        deps["depends_on"]["services"].add(sm.group(1))

            # Exposed routes
            for pattern, style in route_patterns:
                for m in re.finditer(pattern, content, re.IGNORECASE):
                    if style == "nextjs":
                        method = m.group(1).upper()
                        # Infer path from file location
                        path = self._infer_nextjs_route(fi.path) or fi.rel_path
                        deps["exposes"]["api"].append(f"{method} {path}")
                    else:
                        method = m.group(1).upper()
                        path = m.group(2) if len(m.groups()) >= 2 else "/"
                        deps["exposes"]["api"].append(f"{method} {path}")

            # Events
            for m in re.finditer(r'@EventPattern\s*\(\s*[`"\'"]([^`"\'"]+ )', content):
                deps["exposes"]["events"].append(m.group(1))
            for m in re.finditer(r'emit\s*\(\s*[`"\'"]([^`"\'"]+ )', content):
                deps["exposes"]["events"].append(m.group(1))

            # Databases
            for pattern, name in db_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    deps["depends_on"]["databases"].append(name)

            # Message queues
            for pattern, name in mq_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    deps["depends_on"]["message_queues"].append(name)

            # SDKs
            for pattern, name in sdk_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    deps["depends_on"]["external_apis"].append(name)

            # Exported TS types
            for m in re.finditer(r'export\s+(?:interface|type)\s+(\w+)', content):
                name = m.group(1)
                if name not in ("Props", "State", "Context", "Config", "Options"):
                    deps["exposes"]["types"].append(name)

    # ── Rust ──────────────────────────────────────────────────────────────────

    def _detect_rust(self, deps: dict) -> None:
        cargo = self.root / "Cargo.toml"
        if not cargo.exists():
            return
        content = safe_read_text(cargo) or ""
        if re.search(r'reqwest\s*=', content):
            deps["depends_on"]["services"].add("http-client")
        if re.search(r'sqlx\s*=', content):
            deps["depends_on"]["databases"].append("Database (SQLx)")
        if re.search(r'diesel\s*=', content):
            deps["depends_on"]["databases"].append("Database (Diesel)")
        if re.search(r'redis\s*=', content):
            deps["depends_on"]["databases"].append("Redis")
        if re.search(r'tonic\s*=', content):
            deps["depends_on"]["services"].add("grpc")

    # ── Go ────────────────────────────────────────────────────────────────────

    def _detect_go(self, deps: dict) -> None:
        go_mod = self.root / "go.mod"
        if not go_mod.exists():
            return
        content = safe_read_text(go_mod) or ""
        if "net/http" in content or "go-resty" in content:
            deps["depends_on"]["services"].add("http-client")
        if "gorm.io" in content or "database/sql" in content:
            deps["depends_on"]["databases"].append("Database")
        if "go-redis" in content:
            deps["depends_on"]["databases"].append("Redis")
        if "go.mongodb.org" in content:
            deps["depends_on"]["databases"].append("MongoDB")
        if "google.golang.org/grpc" in content:
            deps["depends_on"]["services"].add("grpc")

    # ── Next.js route inference ───────────────────────────────────────────────

    def _infer_nextjs_route(self, filepath: Path) -> Optional[str]:
        s = str(filepath)
        if "/app/api/" in s and "route." in filepath.name:
            m = re.search(r'/app(/api/[^/]+(?:/[^/]+)*)/route\.\w+$', s)
            if m:
                return re.sub(r'\[(\w+)\]', r'{\1}', m.group(1))
        if "/pages/api/" in s:
            m = re.search(r'/pages(/api/[^.]+)\.\w+$', s)
            if m:
                return re.sub(r'\[(\w+)\]', r'{\1}', m.group(1))
        return None
