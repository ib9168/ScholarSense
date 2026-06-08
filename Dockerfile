FROM node:20-slim
RUN npx -y mongodb-mcp-server@latest
ENV MDB_MCP_CONNECTION_STRING=""
ENV MDB_MCP_READ_ONLY="false"
CMD ["npx", "mongodb-mcp-server@latest", "--transport", "sse"]
