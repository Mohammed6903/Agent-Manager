# OpenClaw API — Project Guidelines

## Code Style

**Always follow PEP8** with these conventions:
- Line length: 88 characters (Black formatter standard)
- 4-space indentation
- Double quotes for strings (enforced by Black)
- Comments above code, not inline
- 2 blank lines between top-level definitions

**Code with types** — Type annotations are required:
- Annotate all function parameters and return types
- Use `from __future__ import annotations` at the top of files for modern syntax
- Use `typing.Any`, `typing.Optional`, etc. where appropriate
- Use `|` union syntax (Python 3.10+) for optional types where modern syntax applies

Example:

```python
from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Session

def process_data(user_id: int, data: dict[str, Any]) -> str | None:
    """Process user data and return result or None."""
    return str(data.get("value"))
```

## Architecture

- **Layered structure**: routers → services → repositories → models
- **FastAPI framework** for HTTP APIs and WebSocket connections
- **SQLAlchemy ORM** for database interactions
- **Pydantic schemas** for request/response validation
- **Google APIs** for Gmail, Drive, Calendar, Sheets integrations
- **Alembic migrations** for database schema management

See [docs/](../docs/) for detailed architecture and integration patterns.

## Build and Test

### Setup
```bash
cd /home/mohammed/dev/TechNSure/Garage/server/OpenClawApi
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Run
```bash
python main.py
```

### Test
```bash
pytest
```

### Database Migrations
```bash
alembic upgrade head  # Apply migrations
alembic revision --autogenerate -m "description"  # Create new migration
```

## Conventions

- **Imports**: Organize as: standard library → third-party → local imports, each group separated by blank line
- **Naming**: Use snake_case for variables/functions, PascalCase for classes
- **Docstrings**: All public functions, classes, and modules require docstrings (Google style)
- **Logging**: Use module-level logger: `logger = logging.getLogger(__name__)`
- **Error handling**: Use FastAPI `HTTPException` for API errors; raise clear exceptions with descriptive messages

## Key Files

- `pyproject.toml` — Project metadata and dependencies
- `main.py` — FastAPI application setup
- `agent_manager/config.py` — Environment and configuration
- `agent_manager/schemas/` — Pydantic models for validation
- `agent_manager/services/` — Business logic
- `agent_manager/routers/` — API route handlers
