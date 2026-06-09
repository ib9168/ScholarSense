FROM node:20-slim
WORKDIR /app
RUN npm install -g @mongodb-js/mongodb-mcp-server
ENV MDB_MCP_CONNECTION_STRING=""
ENV MDB_MCP_READ_ONLY="false"
EXPOSE 8080
CMD ["mongodb-mcp-server", "--transport", "http", "--httpHost", "0.0.0.0", "--httpPort", "8080"]
