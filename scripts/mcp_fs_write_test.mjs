/*
 Minimal MCP stdio client to verify write/read against the filesystem MCP server.
 - Spawns: `npx -y @modelcontextprotocol/server-filesystem .`
 - Initializes, then calls `tools/call` for `write_file` and `read_text_file`.
*/
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';

const SERVER_CMD = 'npx';
const HOME = process.env.HOME || process.env.USERPROFILE || '';
if (!HOME) {
  console.error('Unable to determine HOME directory for MCP test');
  process.exit(1);
}
const ALLOWED_DIR = path.join(HOME, 'mcp-test');
const SERVER_ARGS = ['-y', '@modelcontextprotocol/server-filesystem', ALLOWED_DIR];

function createJsonRpcClient(child) {
  let nextId = 1;
  const pending = new Map();
  let stdoutBuf = '';

  child.stdout.setEncoding('utf8');
  child.stderr.setEncoding('utf8');

  child.stdout.on('data', (chunk) => {
    stdoutBuf += chunk;
    let idx;
    while ((idx = stdoutBuf.indexOf('\n')) !== -1) {
      const line = stdoutBuf.slice(0, idx).replace(/\r$/, '');
      stdoutBuf = stdoutBuf.slice(idx + 1);
      if (!line) continue;
      let msg;
      try {
        msg = JSON.parse(line);
      } catch (e) {
        console.error('Non-JSON line from server:', line);
        continue;
      }
      if (msg.id !== undefined && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || 'MCP error'));
        else resolve(msg.result);
      } else {
        // Notifications or unexpected messages; ignore for this simple client.
      }
    }
  });

  child.stderr.on('data', (chunk) => {
    process.stderr.write('[server] ' + chunk);
  });

  function send(msg) {
    child.stdin.write(JSON.stringify(msg) + '\n');
  }

  function request(method, params = undefined) {
    const id = nextId++;
    const msg = { jsonrpc: '2.0', id, method };
    if (params !== undefined) msg.params = params;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      send(msg);
    });
  }

  function notify(method, params = undefined) {
    const msg = { jsonrpc: '2.0', method };
    if (params !== undefined) msg.params = params;
    send(msg);
  }

  return { request, notify };
}

async function main() {
  // Ensure allowed directory exists and is writable
  await fs.mkdir(ALLOWED_DIR, { recursive: true });

  // Start server with current repo as allowed root
  const child = spawn(SERVER_CMD, SERVER_ARGS, { stdio: ['pipe', 'pipe', 'pipe'] });

  const client = createJsonRpcClient(child);

  // Wait briefly to ensure server bootstraps stdio transport
  await new Promise((r) => setTimeout(r, 150));

  // Initialize (use latest protocol version from SDK as of 2025-06-18)
  const init = await client.request('initialize', {
    protocolVersion: '2025-06-18',
    capabilities: {},
    clientInfo: { name: 'codex-mcp-verify', version: '0.1.0' },
  });

  if (!init || !init.capabilities) {
    throw new Error('Invalid initialize result');
  }

  // Notify initialized
  client.notify('notifications/initialized');

  const testPath = path.join(ALLOWED_DIR, 'mcp_write_check.txt');
  const testContent = 'MCP write OK\n';

  // Write file via MCP tool
  const writeRes = await client.request('tools/call', {
    name: 'write_file',
    arguments: { path: testPath, content: testContent },
  });

  // Read it back
  const readRes = await client.request('tools/call', {
    name: 'read_text_file',
    arguments: { path: testPath },
  });

  // Extract text content from result.content array
  const items = (readRes && readRes.content) || [];
  const textItem = items.find((c) => c && c.type === 'text');
  const readText = textItem ? textItem.text : '';

  // Output a compact summary to stdout for the harness
  console.log(JSON.stringify({ ok: true, wrote: testPath, readBack: readText.trim() }));

  // Cleanup: end server process
  child.kill('SIGTERM');
}

main().catch((err) => {
  console.error('MCP verification failed:', err && err.message ? err.message : err);
  process.exit(1);
});
