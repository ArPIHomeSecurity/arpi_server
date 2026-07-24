# AGENTS

## General Project Description
ArPI Server is the Python backend for the ArPI home security system on Raspberry Pi.
It provides REST APIs, monitoring workflows, and MCP integration.
Main stack: Python 3.11, Flask, FastMCP, PostgreSQL, MQTT.

## General Architecture
- src/server: core HTTP API, auth, DB access, business logic.
- src/monitor: monitoring runtime, events, actions, notifications, sensor/output handling.
- src/mcp_server: MCP endpoints, models, auth, prompts.
- migrations: Alembic DB schema migrations.
- tests: pytest suites for startup, arm/disarm, helpers, fixtures.

## How To Run Locally
Prerequisites: Python 3.11, uv, Task, Docker.

1. Install dependencies:
   uv sync --group=dev --extra=simulator
2. Start local infra:
   task start-database
   task start-mqtt
3. Start services as needed:
   task start-server
   task start-monitor
   task start-mcp

## Execute The Tests
Run all tests:
uv run pytest -v

Useful variants:
- task test
- task test-debug

