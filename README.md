# CCC — Code Context Compiler

**Compile your codebase into structured context files that LLMs actually understand.**

Stop pasting entire repositories into prompts.  
CCC extracts the **architecture, APIs, types, and conventions** from your project and turns them into **small high-signal files optimized for LLM workflows.**

---

# What Makes This Different

Most tools give LLMs **more code**.

CCC gives them **the structure of the codebase.**

| Tool | Approach |
|-----|-----|
| Repomix | Concatenates repository files |
| IDE indexing | Search-based |
| CCC | Extracts **semantic context** (types, APIs, architecture) |

Instead of sending 50 source files, you send **3–5 curated context files**.

---

# Example Output

*(Replace these with real output from a project once available.)*

### `routes.txt`

GET /users
POST /users
GET /users/{id}
DELETE /users/{id}

### `schemas-extracted.py`

User:
id: UUID
email: str
created_at: datetime

### `LLM.md`

Error handling: Result pattern
Async usage: heavy
ORM: SQLAlchemy
Testing: pytest

These files provide **the structural map of the codebase**.

---

# Installation

### Single-file install

```bash
curl -O https://raw.githubusercontent.com/yourusername/ccc/main/llm-context-setup.py
python3 llm-context-setup.py
```
Core requirements:

Python 3.10+

No dependencies are required for core functionality.

Optional features:

pip install anthropic
pip install openai
pip install pyyaml
pip install watchdog


⸻

Quick Start

1. Generate context

python3 llm-context-setup.py

2. Result

.llm-context/
  routes.txt
  schemas-extracted.py
  dependency-graph.md
  symbol-index.json

Plus:

CLAUDE.md
ARCHITECTURE.md


⸻

Recommended Workflow

The most effective setup is automatic updates after commits.

Create:

.git/hooks/post-commit

#!/bin/bash

if git diff HEAD~1 --name-only | grep -qE "\.(py|ts|js|rs|go|cs)$"; then
  python3 llm-context-setup.py --quick-update
fi

Make it executable:

chmod +x .git/hooks/post-commit

Now your LLM context stays synchronized with your repository automatically.

⸻

Using Context Files With LLMs

Typical workflow:

Upload the following files when starting an LLM session:
	1.	LLM.md
	2.	ARCHITECTURE.md
	3.	.llm-context/schemas-extracted.py
	4.	.llm-context/routes.txt
	5.	The file you want to modify

This provides the model with:
	•	architecture overview
	•	project conventions
	•	type definitions
	•	API structure

before it reads implementation code.

⸻

What CCC Extracts

CCC analyzes the repository and generates structured context including:

Code Structure
	•	file tree
	•	entry points
	•	symbol index
	•	dependency graph

APIs
	•	REST routes
	•	public function signatures
	•	API contracts

Data Models
	•	schemas
	•	ORM models
	•	database structure

Architecture Signals
	•	frameworks
	•	async patterns
	•	testing tools
	•	logging libraries
	•	dangerous areas (auth, crypto, migrations)

⸻

Security Modes

Three operational modes are supported.

Mode	Description
offline	No external API calls
private-ai	Use internal model infrastructure
public-ai	Enable external API providers

Security features include:
	•	automatic secret redaction
	•	audit logging
	•	binary file detection

⸻

CLI Usage

Basic usage:

python3 llm-context-setup.py

Common commands:

--quick-update
--watch
--force
--doctor
--security-status

Example:

python3 llm-context-setup.py --quick-update


⸻

Configuration

Create a configuration file:

llm-context.yml

Example:

output_dir: .llm-context

security:
  mode: offline

generate:
  routes: true
  schemas: true
  dependencies: true
  symbol_index: true


⸻

Supported Languages

Current extractors support:
	•	Python
	•	TypeScript
	•	Rust
	•	Go
	•	C#

Additional languages can be added through modular extractors.

⸻

Project Structure

your-project/

.llm-context/
  routes.txt
  schemas-extracted.py
  dependency-graph.txt
  symbol-index.json

LLM.md
ARCHITECTURE.md
llm-context.yml
llm-context-setup.py

## What It Does

Generates a `.llm-context/` directory with:

- 📁 **File tree** — Project structure overview
- 🔷 **Type definitions** — Extracted schemas, interfaces, dataclasses
- 🛣️ **API routes** — All endpoints mapped
- 📝 **Public API** — Function signatures across the codebase
- 🔗 **Dependency graph** — Import relationships (text + Mermaid diagram)
- 🌐 **External dependencies** — Service calls, APIs, databases detected  ← NEW!
- 🗺️ **Symbol index** — Navigate classes and functions
- 🎯 **Entry points** — Main files, servers, CLI tools
- 🗄️ **Database schema** — SQLAlchemy, Django, Prisma models
- 📋 **CLAUDE.md** — Auto-detected conventions
- 🏗️ **ARCHITECTURE.md** — System design scaffold

### External Dependencies Detection

The tool automatically detects and documents:

✅ **External API calls** — HTTP requests to other services  
✅ **Service dependencies** — Which external services you call  
✅ **Database connections** — PostgreSQL, MongoDB, Redis, etc.  
✅ **Message queues** — Kafka, RabbitMQ, Celery, etc.  
✅ **Third-party APIs** — Stripe, Twilio, AWS, etc.  
✅ **Exposed APIs** — Endpoints your service provides  
✅ **Auto-detected tags** — Categorization for workspace queries  

**Example `external-dependencies.json`:**

```json
{
  "service": "user-service",
  "exposes": {
    "api": ["GET /api/users/{id}", "POST /api/users"],
    "events": ["user.created", "user.updated"]
  },
  "depends_on": {
    "services": ["auth-service", "notification-service"],
    "apis_consumed": [
      "GET http://auth-service/validate",
      "POST http://notification-service/send"
    ],
    "databases": ["PostgreSQL", "Redis"],
    "message_queues": ["Celery/Redis"]
  },
  "tags": ["backend-api", "users", "python"]
}
```
This file is the foundation for multi-repo mode, enabling workspace queries like:
```
# Find all services tagged "users"
ccc workspace query --tags users

# See what depends on auth-service
ccc workspace query --service auth-service --what depends-on-me
```

⸻
### How to:
#### Test feature on the fixture
1.Navigate to the Python fixture
cd tests/fixtures/python-fastapi

2.Run the generator
python ../../../llm-context-setup.py

3.Check the output
cat .llm-context/external-dependencies.json

You should see:
- Service name detected
- Exposed APIs (/api/users, etc.)
- External service calls (auth-service, notification-service)
- Dependencies detected
- Tags auto-assigned




Roadmap

Planned improvements:
	•	framework-specific extractors
	•	multi-repository mode
	•	MCP server integration
	•	improved dependency analysis

⸻

Contributing

Contributions are welcome.

Areas that benefit most from improvement:
	•	additional language extractors
	•	framework analysis
	•	database schema extraction
	•	architecture detection

⸻

License

MIT

⸻

Start

python3 llm-context-setup.py --doctor
python3 llm-context-setup.py

---
