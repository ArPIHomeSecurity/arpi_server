# ArPI Server 🛡️

<div align="center">

[![CI / Format](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-format.yml/badge.svg)](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-format.yml)
&nbsp;
[![CI / Lint](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-lint.yml/badge.svg)](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-lint.yml)
&nbsp;
[![CI / Test](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-test.yml/badge.svg)](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-test.yml)
&nbsp;
[![CI- CodeQL](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-codeql.yml/badge.svg)](https://github.com/ArPIHomeSecurity/arpi_server/actions/workflows/ci-codeql.yml)

</div>

The backend service of the ArPI Home Security system running on the Raspberry PI.

The system has three services:
* The REST API for communicating with the backend
* The monitor service for executing the business logic
* The MCP server interface for communication with AI agents

### More info:
* 🌐 Project page: https://www.arpi-security.info/
* 🧪 Demo: https://demo.arpi-security.info/
* 📘 Documentation: https://docs.arpi-security.info/


## Overview

This project is built with Python, Flask, and FastMCP. It provides the main API,
monitoring services, and MCP integration for the ArPI security system,
with PostgreSQL-backed persistence and support for MQTT-connected components.


## Prerequisites 🧰
- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- [Docker](https://docs.docker.com/engine/install/)
- [Task](https://taskfile.dev/installation/)



## Local development

Install the Python dependencies and create the local environment file:

```bash
task create-environment
```

Review `.env` and update the hardware, database, and MQTT settings for your
machine. The checked-in values are intended for local development only.

Start the development dependencies in one terminal:

```bash
# starting docker containers
task start-database
task start-mqtt
task start-nginx
```

Start the REST API and monitor service in separate terminals:

```bash
# REST API: http://localhost:8080
task start-server
```

```bash
# Monitor service: http://localhost:8081
task start-monitor
```

The nginx reverse proxy exposes the API and the websocket of the monitro at `https://localhost:8000`.
It uses a self-signed development certificate, so your browser may display a warning.

Optionally start the MCP interface in another terminal:

```bash
# MCP server: http://localhost:7000
task start-mcp
```

Run the test suite with:

```bash
task test
```

Format the code:
```bash
task format
```

---

### ____
<a href="https://www.paypal.me/gkovacs81/">
  <img alt="Support via PayPal" src="https://cdn.rawgit.com/twolfson/paypal-github-button/1.0.0/dist/button.svg"/>
</a>