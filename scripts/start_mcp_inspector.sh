#!/bin/bash

docker start arpi_mcp_inspector || docker run --rm \
  --network=host \
  -it \
  -p 127.0.0.1:6274:6274 \
  -p 127.0.0.1:6277:6277 \
  -e HOST=0.0.0.0 \
  -e MCP_AUTO_OPEN_ENABLED=false \
  --name arpi_mcp_inspector \
  ghcr.io/modelcontextprotocol/inspector:latest
