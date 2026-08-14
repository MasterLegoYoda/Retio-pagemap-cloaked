/**
 * PageMap Pi extension — read-only web access for Pi, no MCP server.
 *
 * Registers four tools that shell out to the `pagemap` CLI:
 *   - pagemap_search       DuckDuckGo search (and other providers)
 *   - pagemap_fetch        Fetch a URL as markdown/text/html/json
 *   - pagemap_batch_fetch  Fetch up to 10 URLs in parallel
 *   - pagemap_sessions     List / close named sessions
 *
 * Interactive tools (get_page_map, execute_action, fill_form, screenshot,
 * multi-tab) are MCP-only and are not exposed here. See
 * `skills/browse-page/SKILL.md` for the MCP path.
 */

import { spawn } from "node:child_process";
import { Type, type Static } from "typebox";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PAGEMAP_BIN = process.env.PAGEMAP_BIN ?? "pagemap";
const DEFAULT_TIMEOUT_MS = 120_000;
const MAX_OUTPUT_BYTES = 200_000;
const LOCALHOST_RE =
  /^(?:[a-z][a-z0-9+.-]*:\/\/)?(?:localhost|127\.0\.0\.1|\[::1\]|::1)(?::\d+)?(?:\/|$)/i;

type RunResult = {
  stdout: string;
  stderr: string;
  code: number;
  timedOut: boolean;
};

async function runPagemap(
  args: string[],
  options: { timeoutMs?: number; signal?: AbortSignal; env?: Record<string, string> } = {},
): Promise<RunResult> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const env = { ...process.env, ...options.env };

  return new Promise((resolve) => {
    const child = spawn(PAGEMAP_BIN, args, { env, stdio: ["ignore", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let killed = false;

    const timer = setTimeout(() => {
      timedOut = true;
      killed = true;
      child.kill("SIGKILL");
    }, timeoutMs);

    const onAbort = () => {
      killed = true;
      child.kill("SIGKILL");
    };
    if (options.signal) {
      if (options.signal.aborted) onAbort();
      else options.signal.addEventListener("abort", onAbort, { once: true });
    }

    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      if (options.signal) options.signal.removeEventListener("abort", onAbort);
      resolve({ stdout, stderr: stderr + `\nspawn error: ${err.message}`, code: 127, timedOut });
    });

    child.on("close", (code) => {
      clearTimeout(timer);
      if (options.signal) options.signal.removeEventListener("abort", onAbort);
      resolve({ stdout, stderr, code: code ?? 1, timedOut: timedOut || killed });
    });
  });
}

function truncate(text: string): string {
  if (text.length <= MAX_OUTPUT_BYTES) return text;
  const head = text.slice(0, MAX_OUTPUT_BYTES);
  return `${head}\n\n[truncated at ${MAX_OUTPUT_BYTES} bytes; rerun with --max-chars to bound]`;
}

function isLikelyLocalhost(url: string): boolean {
  return LOCALHOST_RE.test(url);
}

function userError(text: string, isError = true) {
  return {
    content: [{ type: "text" as const, text }],
    details: {},
    isError,
  };
}

function okResult(text: string) {
  return {
    content: [{ type: "text" as const, text }],
    details: {},
    isError: false,
  };
}

function handleRunResult(result: RunResult, jsonExpected: boolean): {
  content: Array<{ type: "text"; text: string }>;
  details: Record<string, unknown>;
  isError: boolean;
} {
  if (result.timedOut) {
    return userError(`pagemap timed out after ${DEFAULT_TIMEOUT_MS}ms`);
  }
  if (result.code !== 0) {
    const combined = (result.stderr || result.stdout).trim();
    if (/cloakbrowser.*not (yet )?installed/i.test(combined) || /executable doesn't exist/i.test(combined)) {
      return userError("CloakBrowser binary not installed. Run: `cloakbrowser install`");
    }
    return userError(combined || `pagemap exited with code ${result.code}`);
  }
  if (jsonExpected) {
    const out = result.stdout.trim();
    try {
      JSON.parse(out);
    } catch {
      return okResult(truncate(out));
    }
    return okResult(truncate(out));
  }
  return okResult(truncate(result.stdout));
}

const SearchParams = Type.Object({
  query: Type.String({ description: "Search query" }),
  max_results: Type.Optional(Type.Number({ minimum: 1, maximum: 20, default: 10 })),
  recency: Type.Optional(
    Type.Union([
      Type.Literal("day"),
      Type.Literal("week"),
      Type.Literal("month"),
      Type.Literal("year"),
    ]),
  ),
  session: Type.Optional(
    Type.String({ description: "Session id; 'new' or 'new:<name>' for continuity" }),
  ),
  provider: Type.Optional(
    Type.Union([
      Type.Literal("duckduckgo"),
      Type.Literal("brave"),
      Type.Literal("bing"),
      Type.Literal("google"),
      Type.Literal("searxng"),
      Type.Literal("exa"),
      Type.Literal("tavily"),
      Type.Literal("firecrawl"),
    ]),
  ),
  domain: Type.Optional(Type.Array(Type.String())),
  use_browser: Type.Optional(Type.Boolean({ default: false, description: "Render search engine page through CloakBrowser" })),
});
type SearchInput = Static<typeof SearchParams>;

const FetchParams = Type.Object({
  url: Type.String({ description: "http(s) URL to fetch" }),
  format: Type.Optional(
    Type.Union([
      Type.Literal("markdown"),
      Type.Literal("text"),
      Type.Literal("html"),
      Type.Literal("json"),
    ]),
  ),
  max_chars: Type.Optional(Type.Number({ minimum: 100, default: 50_000 })),
  session: Type.Optional(Type.String()),
  mode: Type.Optional(Type.Union([Type.Literal("browser"), Type.Literal("fast")])),
});
type FetchInput = Static<typeof FetchParams>;

const BatchFetchParams = Type.Object({
  urls: Type.Array(Type.String(), { minItems: 1, maxItems: 10 }),
  format: Type.Optional(
    Type.Union([
      Type.Literal("markdown"),
      Type.Literal("text"),
      Type.Literal("html"),
    ]),
  ),
  max_chars: Type.Optional(Type.Number({ minimum: 100, default: 50_000 })),
  max_concurrency: Type.Optional(Type.Number({ minimum: 1, maximum: 5, default: 5 })),
  session: Type.Optional(Type.String()),
  mode: Type.Optional(Type.Union([Type.Literal("browser"), Type.Literal("fast")])),
});
type BatchFetchInput = Static<typeof BatchFetchParams>;

const SessionsParams = Type.Object({
  action: Type.Union([Type.Literal("list"), Type.Literal("close")]),
  session_id: Type.Optional(
    Type.String({ default: "default", description: "Session id to close (default: reset default session)" }),
  ),
});
type SessionsInput = Static<typeof SessionsParams>;

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "pagemap_search",
    label: "PageMap Search",
    description:
      "Web search via DuckDuckGo (default) or other providers. Returns ranked {title,url,snippet} results. Use for lookups, news, and discovery.",
    parameters: SearchParams,
    async execute(_id, params: SearchInput, signal) {
      const args = ["search", "--format", "json", params.query];
      if (params.max_results != null) args.push("--max-results", String(params.max_results));
      if (params.recency) args.push("--recency", params.recency);
      if (params.provider) args.push("--provider", params.provider);
      if (params.domain?.length) {
        for (const d of params.domain) args.push("--domain", d);
      }
      if (params.use_browser) args.push("--use-browser");
      if (params.session) args.push("--session", params.session);
      const result = await runPagemap(args, { signal });
      return handleRunResult(result, true);
    },
  });

  pi.registerTool({
    name: "pagemap_fetch",
    label: "PageMap Fetch",
    description:
      "Fetch a URL and return extracted markdown (default), text, html, or JSON. JS-rendered via CloakBrowser. Use mode='fast' for HTTP-only (no JS).",
    parameters: FetchParams,
    async execute(_id, params: FetchInput, signal) {
      if (isLikelyLocalhost(params.url)) {
        const result = await runPagemap(["fetch", params.url, "--format-output", "json"], {
          signal,
          env: { PAGEMAP_ALLOW_LOCAL: "1" },
        });
        return handleRunResult(result, true);
      }
      const args = ["fetch", params.url, "--format-output", "json"];
      if (params.format) args.push("--format", params.format);
      if (params.max_chars != null) args.push("--max-chars", String(params.max_chars));
      if (params.mode) args.push("--mode", params.mode);
      if (params.session) args.push("--session", params.session);
      const result = await runPagemap(args, { signal });
      return handleRunResult(result, true);
    },
  });

  pi.registerTool({
    name: "pagemap_batch_fetch",
    label: "PageMap Batch Fetch",
    description:
      "Fetch up to 10 URLs in parallel (max 5 concurrent). Same outputs as pagemap_fetch.",
    parameters: BatchFetchParams,
    async execute(_id, params: BatchFetchInput, signal) {
      const env: Record<string, string> = {};
      if (params.urls.some(isLikelyLocalhost)) env.PAGEMAP_ALLOW_LOCAL = "1";
      const args = ["batch-fetch", "--format-output", "json", ...params.urls];
      if (params.format) args.push("--format", params.format);
      if (params.max_chars != null) args.push("--max-chars", String(params.max_chars));
      if (params.mode) args.push("--mode", params.mode);
      if (params.max_concurrency != null)
        args.push("--max-concurrency", String(params.max_concurrency));
      if (params.session) args.push("--session", params.session);
      const result = await runPagemap(args, { signal, env });
      return handleRunResult(result, true);
    },
  });

  pi.registerTool({
    name: "pagemap_sessions",
    label: "PageMap Sessions",
    description:
      "List active web sessions or close one by id. Use 'default' to reset the default session.",
    parameters: SessionsParams,
    async execute(_id, params: SessionsInput, signal) {
      if (params.action === "list") {
        const result = await runPagemap(["sessions", "list", "--format", "json"], { signal });
        return handleRunResult(result, true);
      }
      const result = await runPagemap(
        ["sessions", "close", params.session_id ?? "default"],
        { signal },
      );
      return handleRunResult(result, false);
    },
  });
}