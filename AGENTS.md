# AGENTS

## General Project Description
ArPI Server is the Python backend for the ArPI home security system on Raspberry Pi.
It provides REST APIs, monitoring workflows, and MCP integration.
Main stack: Python 3.12+, Flask, FastMCP, PostgreSQL, MQTT.

## General Architecture
- src/server: core HTTP API, auth, DB access, business logic.
- src/monitor: monitoring runtime, events, actions, notifications, sensor/output handling.
- src/mcp_server: MCP endpoints, models, auth, prompts.
- migrations: Alembic DB schema migrations.
- tests: pytest suites for startup, arm/disarm, helpers, fixtures.

## How To Run Locally
Prerequisites: Python 3.12+, uv, Task, Docker.

1. Install dependencies:
   uv sync --group=dev --extra=simulator
2. Start local infra:
   task start:database
   task start:mqtt
3. Start services as needed:
   task start:server
   task start:monitor
   task start:mcp

## Execute The Tests
Run all tests:
uv run --env-file .env.pytest pytest -v

Useful variants:
- task test:all
- task test:debug
- task test:all -- -k <test-filter>
- task test:debug -- -k <test-filter>

# Notes

* When executing commands in the project always use the `uv` command (with .env loaded) or `task` command to ensure the correct environment and dependencies are used.
* The `uv` command ensures that the Python environment is correctly set up with the necessary dependencies for development and testing.
