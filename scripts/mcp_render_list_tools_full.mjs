/*
 Prints the full tools list (names + input schemas) from the Render MCP server.
*/
import { spawn } from 'node:child_process';

const CMD = process.env.RENDER_MCP_CMD || 'render-mcp-server';
const ARGS = (process.env.RENDER_MCP_ARGS || '').split(' ').filter(Boolean);

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
      try { msg = JSON.parse(line); } catch { continue; }
      if (msg.id !== undefined && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || 'MCP error'));
        else resolve(msg.result);
      }
    }
  });
  child.stderr.on('data', (chunk) => process.stderr.write('[server] ' + chunk));
  function send(msg) { child.stdin.write(JSON.stringify(msg) + '\n'); }
  function request(method, params) {
    const id = nextId++;
    const msg = { jsonrpc: '2.0', id, method };
    if (params !== undefined) msg.params = params;
    return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); send(msg); });
  }
  function notify(method, params) { const msg = { jsonrpc: '2.0', method }; if (params) msg.params = params; send(msg); }
  return { request, notify };
}

async function main() {
  if (!process.env.RENDER_API_KEY) {
    console.error('Set RENDER_API_KEY');
    process.exit(1);
  }
  const child = spawn(CMD, ARGS, { stdio: ['pipe','pipe','pipe'], env: { ...process.env } });
  const client = createJsonRpcClient(child);
  await new Promise((r) => setTimeout(r, 150));
  await client.request('initialize', { protocolVersion: '2025-06-18', capabilities: { tools: {} }, clientInfo: { name: 'codex-mcp-tools', version: '0.1.0' } });
  client.notify('notifications/initialized');

  const tools = await client.request('tools/list', {});
  console.log(JSON.stringify({ ok: true, tools: tools.tools }, null, 2));
  child.kill('SIGTERM');
}

main().catch((err) => { console.error('List tools failed:', err?.message || err); process.exit(1); });

