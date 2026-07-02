# Copyright (C) 2025-2026 Retio AI
# SPDX-License-Identifier: AGPL-3.0-only

"""Page Map CLI: try, build, serve, setup, auth, benchmark, collect, convert commands.

Usage:
    python -m pagemap.cli try URL [--format text|json|markdown]
    python -m pagemap.cli build [--url URL] [--snapshots] [--output DIR]
    python -m pagemap.cli serve
    python -m pagemap.cli setup {claude-code,cursor,windsurf,vscode,claude-desktop}
    python -m pagemap.cli validate [--url URL] [--all]
    python -m pagemap.cli benchmark [--static] [--live] [--task ID] [--model MODEL]
    python -m pagemap.cli collect [--site SITE] [--type TYPE] [--count N] [--all] [--simulator]
    python -m pagemap.cli convert [--tool TOOL] [--snapshot-dir DIR] [--force] [--pilot]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path


def _require_cli_deps() -> None:
    """Check that CLI optional dependencies are installed."""
    try:
        import yaml  # noqa: F401
        from tabulate import tabulate  # noqa: F401
    except ImportError as e:
        print(
            f"Missing CLI dependency: {e.name}\nInstall with: pip install retio-pagemap[cli]",
            file=sys.stderr,
        )
        sys.exit(1)


def _validate_output_path(path_str: str | None) -> tuple[Path | None, bool]:
    """Validate and return an output path with file-mode flag.

    Returns:
        (path, is_file_mode): path is None if not specified.
        is_file_mode is True when path has a suffix (e.g., out.json).
    """
    if not path_str:
        return None, False
    p = Path(path_str)
    is_file = bool(p.suffix)
    parent = p.parent if is_file else p
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    return p, is_file


def _has_internal() -> bool:
    """Check if internal development modules are available."""
    try:
        from ._internal import collect  # noqa: F401

        return True
    except ImportError:
        return False


def _has_benchmark() -> bool:
    """Check if benchmark modules are available."""
    try:
        from ._internal import benchmark  # noqa: F401

        return True
    except ImportError:
        return False


def _benchmark_postflight(
    result: object,
    tasks: list[dict],
    report_func: callable,
    save_func: callable,
    result_path: Path,
    report_path: Path,
) -> str:
    """Common benchmark post-processing: evaluate, report, save."""
    from ._internal.benchmark.evaluator import evaluate_all

    evaluate_all(tasks, result.task_results)
    report = report_func(result, tasks)
    print("\n" + report)
    save_func(result, result_path)
    report_path.write_text(report)
    print(f"\nResults saved to {result_path.parent}")
    return report


def _has_management_db() -> bool:
    """Check if a management database is configured (SUPABASE_DB_URL)."""
    import os

    return bool(os.environ.get("SUPABASE_DB_URL", ""))


def _require_user_id() -> str:
    """Return PAGEMAP_CLI_USER_ID or exit with error."""
    import os

    user_id = os.environ.get("PAGEMAP_CLI_USER_ID", "")
    if not user_id:
        print("Error: PAGEMAP_CLI_USER_ID environment variable is required.", file=sys.stderr)
        sys.exit(1)
    return user_id


async def _open_repo():
    """Open SupabaseRepository from environment or exit."""
    from .supabase_config import SupabaseConfig

    config = SupabaseConfig.from_env()
    if config is None:
        print("Error: SUPABASE_DB_URL not configured.", file=sys.stderr)
        sys.exit(1)
    from .repository_supabase import SupabaseRepository

    return await SupabaseRepository.create(config)


def cmd_credits(args: argparse.Namespace) -> None:
    """Manage credits — balance and top-up."""
    user_id = _require_user_id()

    if args.credits_command == "balance":
        asyncio.run(_cmd_credits_balance(user_id))
    elif args.credits_command == "topup":
        asyncio.run(_cmd_credits_topup(user_id, args.price_id, getattr(args, "open", False)))


async def _cmd_credits_balance(user_id: str) -> None:
    """Show credit balance for the user."""
    repo = await _open_repo()
    try:
        user = await repo.get_user(user_id)
        if user is None:
            print(f"Error: User '{user_id}' not found.", file=sys.stderr)
            sys.exit(1)

        keys = await repo.list_keys_for_owner(owner_id=user_id)
        print(f"User: {user.email} ({user.plan.value})")
        print(f"Keys: {len(keys)}")
        total = 0
        for k in keys:
            balance = await repo.get_credit_state(k.key_hash)
            status = " (revoked)" if k.revoked else ""
            b = balance if balance is not None else 0
            total += b
            print(f"  {k.key_hash[:12]}... {k.label}: {b} credits{status}")
        print(f"Total: {total} credits")
    finally:
        await repo.close()


async def _cmd_credits_topup(user_id: str, price_id: str, open_url: bool) -> None:
    """Create a checkout session for credit top-up."""
    from .paddle.config import PaddleConfig

    paddle_config = PaddleConfig.from_env()
    if paddle_config is None:
        print("Error: PADDLE_WEBHOOK_SECRET not configured.", file=sys.stderr)
        sys.exit(1)

    repo = await _open_repo()
    try:
        user = await repo.get_user(user_id)
        if user is None:
            print(f"Error: User '{user_id}' not found.", file=sys.stderr)
            sys.exit(1)

        keys = await repo.list_keys_for_owner(owner_id=user_id)
        active_keys = [k for k in keys if not k.revoked]
        if not active_keys:
            print("Error: No active API keys found. Create a key first.", file=sys.stderr)
            sys.exit(1)

        key_hash = active_keys[0].key_hash
        from .paddle.checkout import create_checkout_session

        session = create_checkout_session(paddle_config, key_hash, price_id)
        print(f"Checkout URL: {session.checkout_url}")
        print(f"Transaction ID: {session.transaction_id}")

        if open_url and session.checkout_url:
            import webbrowser

            webbrowser.open(session.checkout_url)
    finally:
        await repo.close()


# ---------------------------------------------------------------------------
# keys / usage / user commands
# ---------------------------------------------------------------------------


def cmd_keys(args: argparse.Namespace) -> None:
    """Manage API keys — list, create, revoke, rotate."""
    user_id = _require_user_id()
    sub = args.keys_command
    if sub == "list":
        asyncio.run(_cmd_keys_list(user_id))
    elif sub == "create":
        asyncio.run(_cmd_keys_create(user_id, args.label, getattr(args, "expires_in_days", None)))
    elif sub == "revoke":
        asyncio.run(_cmd_keys_revoke(user_id, args.key_hash))
    elif sub == "rotate":
        asyncio.run(_cmd_keys_rotate(user_id, args.key_hash, args.label))


async def _cmd_keys_list(user_id: str) -> None:
    repo = await _open_repo()
    try:
        keys = await repo.list_keys_for_owner(owner_id=user_id)
        if not keys:
            print("No API keys found.")
            return
        import datetime

        from tabulate import tabulate

        rows = []
        for k in keys:
            status = "revoked" if k.revoked else "active"
            dt = datetime.datetime.fromtimestamp(k.created_at, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            rows.append([k.key_hash[:12] + "...", k.label, status, dt])
        print(tabulate(rows, headers=["Key Hash", "Label", "Status", "Created"], tablefmt="simple"))
    finally:
        await repo.close()


async def _cmd_keys_create(user_id: str, label: str, expires_in_days: int | None) -> None:
    import time as _time

    from .api_key import KeyRecord, KeyVersion, generate_api_key

    repo = await _open_repo()
    try:
        display_key, key_hash = generate_api_key()
        expires_at = _time.time() + expires_in_days * 86400 if expires_in_days else None
        record = KeyRecord(
            key_hash=key_hash,
            label=label,
            version=KeyVersion.V1,
            created_at=_time.time(),
            expires_at=expires_at,
        )
        await repo.store_key_for_owner(record, user_id)
        print(f"API Key: {display_key}")
        print(f"Key Hash: {key_hash}")
        print("Store the API key securely — it cannot be retrieved later.")
    finally:
        await repo.close()


async def _cmd_keys_revoke(user_id: str, key_hash: str) -> None:
    repo = await _open_repo()
    try:
        ok = await repo.revoke_key_for_owner(key_hash, owner_id=user_id)
        if ok:
            print(f"Key {key_hash[:12]}... revoked.")
        else:
            print("Error: Key not found or already revoked.", file=sys.stderr)
            sys.exit(1)
    finally:
        await repo.close()


async def _cmd_keys_rotate(user_id: str, old_key_hash: str, label: str) -> None:
    import time as _time

    from .api_key import KeyRecord, KeyVersion, generate_api_key

    repo = await _open_repo()
    try:
        # Create new key first (safe: old key still works)
        display_key, key_hash = generate_api_key()
        record = KeyRecord(
            key_hash=key_hash,
            label=label,
            version=KeyVersion.V1,
            created_at=_time.time(),
        )
        await repo.store_key_for_owner(record, user_id)
        # Then revoke old key
        ok = await repo.revoke_key_for_owner(old_key_hash, owner_id=user_id)
        if not ok:
            print(f"Warning: Old key {old_key_hash[:12]}... not found or already revoked.", file=sys.stderr)
        print(f"New API Key: {display_key}")
        print(f"New Key Hash: {key_hash}")
        if ok:
            print(f"Old key {old_key_hash[:12]}... revoked.")
    finally:
        await repo.close()


def cmd_usage(args: argparse.Namespace) -> None:
    """Show usage statistics."""
    user_id = _require_user_id()
    asyncio.run(_cmd_usage(user_id, getattr(args, "period", None)))


async def _cmd_usage(user_id: str, period: str | None) -> None:
    import time as _time

    repo = await _open_repo()
    try:
        keys = await repo.list_keys_for_owner(owner_id=user_id)
        if not keys:
            print("No API keys found.")
            return

        if period:
            from .time_utils import parse_period

            total_s, bucket_s = parse_period(period)
            now = _time.time()
            since = now - total_s
            from tabulate import tabulate

            for k in keys:
                buckets = await repo.get_usage_timeseries(
                    k.key_hash,
                    since_ts=since,
                    until_ts=now,
                    bucket_seconds=bucket_s,
                )
                print(f"\nKey: {k.key_hash[:12]}... ({k.label})")
                if not buckets:
                    print("  No usage in this period.")
                    continue
                import datetime

                rows = []
                for b in buckets:
                    dt = datetime.datetime.fromtimestamp(b.bucket_start, tz=datetime.UTC)
                    rows.append([dt.strftime("%Y-%m-%d %H:%M"), b.call_count, b.total_cost])
                print(tabulate(rows, headers=["Period Start", "Calls", "Cost"], tablefmt="simple"))
        else:
            from tabulate import tabulate

            for k in keys:
                stats = await repo.get_usage_stats(k.key_hash)
                print(f"\nKey: {k.key_hash[:12]}... ({k.label})")
                if not stats:
                    print("  No usage recorded.")
                    continue
                rows = [[s.tool, s.count, s.total_cost] for s in stats]
                print(tabulate(rows, headers=["Tool", "Calls", "Cost"], tablefmt="simple"))
    finally:
        await repo.close()


def cmd_user(args: argparse.Namespace) -> None:
    """Show user info."""
    user_id = _require_user_id()
    asyncio.run(_cmd_user(user_id))


async def _cmd_user(user_id: str) -> None:
    repo = await _open_repo()
    try:
        user = await repo.get_user(user_id)
        if user is None:
            print(f"Error: User '{user_id}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"User ID:    {user.id}")
        print(f"Email:      {user.email}")
        print(f"Name:       {user.name}")
        print(f"Plan:       {user.plan.value}")
        import datetime

        created = (
            datetime.datetime.fromtimestamp(user.created_at, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            if user.created_at
            else "N/A"
        )
        updated = (
            datetime.datetime.fromtimestamp(user.updated_at, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
            if user.updated_at
            else "N/A"
        )
        print(f"Created:    {created}")
        print(f"Updated:    {updated}")
    finally:
        await repo.close()


def cmd_validate(args: argparse.Namespace) -> None:
    """Run AX Tree validation (Day 0)."""
    _require_cli_deps()
    import yaml

    from ._internal.validate_axtree import print_validation_report, validate_urls

    config_path = Path(__file__).parent / "core" / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if args.url:
        urls = [args.url]
    elif args.all:
        from ._internal.collect import _resolve_url_map

        urls = []
        for _site_id, site in config["sites"].items():
            if site.get("collection") == "manual_only":
                continue
            url_map = _resolve_url_map(site)
            for page_urls in url_map.values():
                urls.extend(page_urls[:1])
    else:
        from ._internal.collect import _resolve_url_map

        url_map = _resolve_url_map(config["sites"]["coupang"])
        urls = list(url_map.values())[0][:1] if url_map else []

    results = asyncio.run(validate_urls(urls))
    print_validation_report(results)

    if args.save:
        save_path, _ = _validate_output_path(args.save)
        save_data = [
            {
                "url": r.url,
                "tier12_count": r.tier12_count,
                "tier3_count": r.tier3_count,
                "coverage": r.tier12_coverage,
            }
            for r in results
        ]
        save_path.write_text(json.dumps(save_data, ensure_ascii=False, indent=2))
        print(f"\nSaved to {save_path}")


def cmd_try(args: argparse.Namespace) -> None:
    """Try PageMap on a URL — zero-config demo."""
    url = args.url
    fmt = args.format
    try:
        asyncio.run(_build_live(url, fmt=fmt))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        if _is_browser_binary_missing(e):
            print(
                "CloakBrowser binary not installed.\nRun:  cloakbrowser install\nThen: pagemap try <URL>",
                file=sys.stderr,
            )
        else:
            from .problem_details import from_exception

            problem = from_exception(e, tool_context="try")
            print(problem.to_cli_text(), file=sys.stderr)
        sys.exit(1)

    from ._progress import print_step

    print_step("")
    print_step("Get an API key for higher limits: https://retio.ai")
    print_step("Docs: https://github.com/Retio-ai/Retio-pagemap")


def _is_browser_binary_missing(e: Exception) -> bool:
    """Check if the error is due to missing browser binaries."""
    msg = str(e).lower()
    return "executable doesn't exist" in msg or "cloakbrowser" in msg and "install" in msg


# ── Web fetch / search CLI commands ──────────────────────────────────


def _print_web_error(prefix: str, exc: Exception) -> None:
    """Print a web_fetch CLI error in a single line, fall back to problem details."""
    msg = str(exc).strip()
    if msg:
        print(f"{prefix}: {msg}", file=sys.stderr)
    else:
        print(prefix, file=sys.stderr)


def cmd_search(args: argparse.Namespace) -> None:
    """``pagemap search`` — run a web search and print the results."""
    from pagemap.web_fetch.errors import ProviderError

    try:
        asyncio.run(_cmd_search_async(args))
    except KeyboardInterrupt:
        raise
    except ProviderError as exc:
        _print_web_error("Error", exc)
        sys.exit(1)
    except Exception as exc:  # nosec B110 — CLI surface
        if _is_browser_binary_missing(exc):
            print(
                "CloakBrowser binary not installed.\nRun:  cloakbrowser install\nThen: pagemap search <query>",
                file=sys.stderr,
            )
        else:
            _print_web_error("Error", exc)
        sys.exit(1)


async def _cmd_search_async(args: argparse.Namespace) -> None:
    from pagemap.web_fetch import WebSearchResult
    from pagemap.web_fetch.providers import get_provider
    from pagemap.web_fetch.providers.base import ProviderContext
    from pagemap.web_fetch.sessions import resolve_session_arg

    from .server.browser_session import BrowserSession
    from .server.web_fetch_bridge import attach_browser_to_session

    provider_name = args.provider
    session_arg = getattr(args, "session", None)
    max_results = max(1, min(args.max_results or 10, 20))
    domain_filter = args.domain or None

    # Lazy: only spin up a browser when the user asked for one. Most
    # search providers can work over stdlib HTTP without Chromium.
    need_browser = bool(args.use_browser)

    manager_mod = __import__("pagemap.web_fetch", fromlist=["SessionManager"])
    manager = manager_mod.SessionManager()

    sess, _created = resolve_session_arg(session_arg, manager=manager)

    if need_browser:
        # Validate that the user isn't asking for SSRF on the search engine URL.
        # (The provider itself decides the actual endpoint.)
        # Reuse the existing PageMap browser launcher.
        browser = BrowserSession()
        try:
            await browser.start()
        except Exception as exc:  # nosec B110
            print(f"Error: failed to launch browser: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            attach_browser_to_session(sess, browser)
            prov = get_provider(provider_name)
            ctx = ProviderContext(
                session_id=sess.id,
                history=sess.history + [{"page": browser.page}],
                min_delay_ms=0,
            )
            results = await prov.search(
                args.query,
                max_results=max_results,
                recency=args.recency,
                domain_filter=domain_filter,
                ctx=ctx,
            )
        finally:
            await browser.stop()
    else:
        prov = get_provider(provider_name)
        ctx = ProviderContext(
            session_id=sess.id,
            history=sess.history,
            min_delay_ms=0,
        )
        results = await prov.search(
            args.query,
            max_results=max_results,
            recency=args.recency,
            domain_filter=domain_filter,
            ctx=ctx,
        )

    sess.record("search", query=args.query, provider=provider_name, count=len(results))

    if args.format == "json":
        payload = {
            "query": args.query,
            "provider": provider_name,
            "session": sess.id,
            "result_count": len(results),
            "results": [
                WebSearchResult(title=r.get("title", ""), url=r.get("url", ""), snippet=r.get("snippet", ""), source=provider_name).model_dump()
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    # Default: markdown.
    print(f"# Search: {args.query}")
    print(f"_provider={provider_name} session={sess.id} results={len(results)}_")
    print()
    for i, r in enumerate(results, start=1):
        title = r.get("title", "(no title)")
        url = r.get("url", "")
        snippet = (r.get("snippet") or "").strip()
        print(f"{i}. [{title}]({url})")
        if snippet:
            print(f"   {snippet}")


def cmd_fetch(args: argparse.Namespace) -> None:
    """``pagemap fetch`` — fetch a URL and print the extracted content."""
    try:
        asyncio.run(_cmd_fetch_async(args))
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # nosec B110
        if _is_browser_binary_missing(exc):
            print(
                "CloakBrowser binary not installed.\nRun:  cloakbrowser install\nThen: pagemap fetch <url>",
                file=sys.stderr,
            )
        else:
            _print_web_error("Error", exc)
        sys.exit(1)


async def _cmd_fetch_async(args: argparse.Namespace) -> None:
    from pagemap.web_fetch import FetchFormat
    from pagemap.web_fetch.extract import extract as _extract
    from pagemap.web_fetch.models import WebFetchResult
    from pagemap.web_fetch.sessions import resolve_session_arg

    from .server.browser_session import BrowserSession
    from .server.url_validation import _validate_url
    from .server.web_fetch_bridge import attach_browser_to_session

    mode = (args.mode or "browser").lower()
    fmt = FetchFormat(args.format or "markdown")
    max_chars = args.max_chars or 50_000

    if mode == "fast":
        print(
            "Error: mode='fast' is not yet implemented. Use mode='browser' for now.",
            file=sys.stderr,
        )
        sys.exit(1)

    # SSRF pre-check.
    err = _validate_url(args.url)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    manager_mod = __import__("pagemap.web_fetch", fromlist=["SessionManager"])
    manager = manager_mod.SessionManager()
    sess, _created = resolve_session_arg(getattr(args, "session", None), manager=manager)

    if mode == "browser":
        browser = BrowserSession()
        try:
            await browser.start()
        except Exception as exc:  # nosec B110
            print(f"Error: failed to launch browser: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            attach_browser_to_session(sess, browser)
            page = browser.page
            response = await page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response is not None else None
            content_type = (
                response.headers.get("content-type") if response is not None else None
            )
            final_url = page.url
            post_err = _validate_url(final_url)
            if post_err:
                print(f"Error: redirect to blocked URL — {post_err}", file=sys.stderr)
                sys.exit(1)
            title = await page.title()
            raw_html = await page.content()
        finally:
            await browser.stop()
    else:
        print(f"Error: unknown mode '{mode}'", file=sys.stderr)
        sys.exit(1)

    extracted = _extract(
        raw_html=raw_html or "",
        url=final_url or args.url,
        fmt=fmt,
        max_chars=max_chars,
    )
    sess.record(
        "fetch",
        url=args.url,
        final_url=final_url,
        mode=mode,
        format=fmt.value,
        truncated=extracted.truncated,
        chars=extracted.content_length,
    )

    if args.format == "json" or args.format_output == "json":
        result = WebFetchResult(
            url=args.url,
            final_url=final_url or args.url,
            title=extracted.title or title,
            content_type=content_type,
            status=status,
            session=sess.id,
            session_created=_created,
            format=fmt.value,
            mode=mode,
            content=extracted.content,
            content_length=extracted.content_length,
            truncated=extracted.truncated,
            full_output_path=extracted.full_output_path,
            warnings=extracted.warnings,
        )
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        return

    if extracted.title:
        print(f"# {extracted.title}")
        print()
    print(extracted.content)
    if extracted.truncated and extracted.full_output_path:
        print(
            f"\n[Truncated to {extracted.content_length} chars. Full output: {extracted.full_output_path}]",
            file=sys.stderr,
        )


def cmd_batch_fetch(args: argparse.Namespace) -> None:
    """``pagemap batch-fetch`` — fetch multiple URLs in parallel."""
    try:
        asyncio.run(_cmd_batch_fetch_async(args))
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # nosec B110
        _print_web_error("Error", exc)
        sys.exit(1)


async def _cmd_batch_fetch_async(args: argparse.Namespace) -> None:
    from pagemap.web_fetch import FetchFormat
    from pagemap.web_fetch.extract import extract as _extract
    from pagemap.web_fetch.sessions import resolve_session_arg

    from .server.browser_session import BrowserSession
    from .server.url_validation import _validate_url

    fmt = FetchFormat(args.format or "markdown")
    max_chars = args.max_chars or 50_000
    mode = (args.mode or "browser").lower()
    if mode == "fast":
        print("Error: mode='fast' is not yet implemented.", file=sys.stderr)
        sys.exit(1)

    manager_mod = __import__("pagemap.web_fetch", fromlist=["SessionManager"])
    manager = manager_mod.SessionManager()
    sess, _created = resolve_session_arg(getattr(args, "session", None), manager=manager)

    if args.output:
        try:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # nosec B110
            print(f"Error: bad output path: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        out = None

    concurrency = max(1, min(args.max_concurrency or 5, 5))
    sem = asyncio.Semaphore(concurrency)

    browser = BrowserSession()
    try:
        await browser.start()
    except Exception as exc:  # nosec B110
        print(f"Error: failed to launch browser: {exc}", file=sys.stderr)
        sys.exit(1)

    async def _one(u: str) -> tuple[str, bool, str, str | None]:
        async with sem:
            if not u.lower().startswith(("http://", "https://")):
                return u, False, "url must start with http:// or https://", None
            err = _validate_url(u)
            if err:
                return u, False, err, None
            try:
                page = browser.page
                await page.goto(u, wait_until="domcontentloaded", timeout=30000)
                post_err = _validate_url(page.url)
                if post_err:
                    return u, False, f"redirect to blocked URL: {post_err}", None
                raw_html = await page.content()
            except Exception as exc:  # nosec B110
                return u, False, str(exc), None
            extracted = _extract(raw_html=raw_html, url=page.url or u, fmt=fmt, max_chars=max_chars)
            return u, True, extracted.content, extracted.title

    try:
        results = await asyncio.gather(*[_one(u) for u in args.urls])
    finally:
        await browser.stop()

    succeeded = sum(1 for _, ok, *_ in results if ok)
    failed = len(results) - succeeded
    sess.record("batch_fetch", urls=list(args.urls), succeeded=succeeded, failed=failed)

    if args.format_output == "json":
        payload = {
            "total": len(args.urls),
            "succeeded": succeeded,
            "failed": failed,
            "session": sess.id,
            "results": [
                {"url": u, "success": ok, "title": title, "content": content if ok else None, "error": (content if not ok else None)}
                for (u, ok, content, title) in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if out is not None:
        # Write one file per URL.
        for u, ok, content, title in results:
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", u)[:80]
            path = out / f"{safe}.md"
            path.write_text(
                f"# {title or u}\n\n{content}\n" if ok else f"# ERROR: {u}\n\n{content}\n",
                encoding="utf-8",
        )
        print(
            f"{succeeded} succeeded, {failed} failed. Wrote to {out}",
            file=sys.stderr,
        )
        return

    for u, ok, content, title in results:
        print(f"--- {u} {'(ok)' if ok else '(failed)'} ---")
        if title:
            print(f"# {title}")
        print(content)
        print()


def cmd_sessions(args: argparse.Namespace) -> None:
    """``pagemap sessions list`` / ``pagemap sessions close`` — manage web sessions."""
    from pagemap.web_fetch import SessionManager

    if args.sessions_command == "list":
        manager = SessionManager()
        sessions = manager.list_sessions()
        if args.format == "json":
            print(
                json.dumps(
                    {"sessions": [s.info().model_dump() for s in sessions]},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            if not sessions:
                print("No active web sessions.")
                return
            for s in sessions:
                tag = " (default)" if s.is_default else ""
                print(f"{s.id}{tag}  history={len(s.history)}  last_used={s.last_used:.0f}")
    elif args.sessions_command == "close":
        manager = SessionManager()
        if args.session_id == "default":
            manager.reset_default()
            print("Reset default session.")
        else:
            ok = manager.close(args.session_id)
            if not ok:
                print(f"Error: session '{args.session_id}' not found.", file=sys.stderr)
                sys.exit(1)
            print(f"Closed session '{args.session_id}'.")
    else:
        print(f"Unknown subcommand: {args.sessions_command}", file=sys.stderr)
        sys.exit(1)


def cmd_build(args: argparse.Namespace) -> None:
    """Build Page Maps from URLs or snapshots."""
    output_path, is_file_mode = _validate_output_path(args.output)
    fmt = getattr(args, "format", None)

    # --format sends output to stdout; --output saves to file/dir
    if fmt and output_path:
        print("Error: --format and --output are mutually exclusive.", file=sys.stderr)
        sys.exit(1)

    if not fmt and not is_file_mode:
        output_dir = output_path or Path(__file__).parent / "data"
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = None

    snapshot_dir = Path(args.snapshot_dir) if getattr(args, "snapshot_dir", None) else None

    if args.url:
        try:
            asyncio.run(
                _build_live(
                    args.url,
                    output_dir=output_dir,
                    output_file=output_path if is_file_mode else None,
                    fmt=fmt,
                )
            )
        except KeyboardInterrupt:
            raise
        except Exception as e:
            from .problem_details import from_exception

            problem = from_exception(e, tool_context="build")
            print(problem.to_cli_text(), file=sys.stderr)
            sys.exit(1)
    elif args.snapshots:
        if output_dir is None:
            output_dir = Path(__file__).parent / "data"
            output_dir.mkdir(parents=True, exist_ok=True)
        asyncio.run(_build_from_snapshots(output_dir, snapshot_dir=snapshot_dir))
    elif getattr(args, "offline", False):
        if output_dir is None:
            output_dir = Path(__file__).parent / "data"
            output_dir.mkdir(parents=True, exist_ok=True)
        _build_offline(output_dir)
    else:
        # #9b: --url is required for build
        print(
            "Error: --url is required for the build command.\n\n"
            "Examples:\n"
            "  python -m pagemap.cli build --url https://example.com\n"
            "  python -m pagemap.cli build --url https://example.com --format json\n"
            "  python -m pagemap.cli build --url https://example.com --output result.json\n",
            file=sys.stderr,
        )
        sys.exit(1)


async def _build_live(
    url: str,
    output_dir: Path | None = None,
    output_file: Path | None = None,
    fmt: str | None = None,
) -> None:
    """Build Page Map from live URL."""
    from ._progress import print_step, status_spinner
    from .browser_session import BrowserSession
    from .page_map_builder import build_page_map_live
    from .serializer import to_agent_prompt, to_json

    with status_spinner(f"Building Page Map for {url}..."):
        async with BrowserSession() as session:
            page_map = await build_page_map_live(session, url)

    if fmt:
        # --format: output to stdout, status to stderr
        if fmt == "json":
            print(to_json(page_map))
        elif fmt == "markdown":
            print(to_agent_prompt(page_map, include_meta=True))
        else:  # text
            print(to_agent_prompt(page_map, include_meta=False))
        print_step(f"Interactables: {page_map.total_interactables}")
        print_step(f"Pruned tokens: {page_map.pruned_tokens}")
        print_step(f"Generation: {page_map.generation_ms:.0f}ms")
    elif output_file:
        # --output file mode: single file
        if output_file.suffix == ".json":
            output_file.write_text(to_json(page_map), encoding="utf-8")
        else:
            output_file.write_text(to_agent_prompt(page_map, include_meta=True), encoding="utf-8")
        print(f"Page Map saved to {output_file}")
        print(f"\nInteractables: {page_map.total_interactables}")
        print(f"Pruned tokens: {page_map.pruned_tokens}")
        print(f"Generation: {page_map.generation_ms:.0f}ms")
    else:
        # --output dir mode (default)
        assert output_dir is not None
        json_path = output_dir / "live_page_map.json"
        json_path.write_text(to_json(page_map), encoding="utf-8")

        prompt_path = output_dir / "live_page_map.txt"
        prompt_path.write_text(to_agent_prompt(page_map, include_meta=True), encoding="utf-8")

        print(f"Page Map saved to {json_path}")
        print(f"Agent prompt saved to {prompt_path}")
        print(f"\nInteractables: {page_map.total_interactables}")
        print(f"Pruned tokens: {page_map.pruned_tokens}")
        print(f"Generation: {page_map.generation_ms:.0f}ms")


async def _build_from_snapshots(output_dir: Path, snapshot_dir: Path | None = None) -> None:
    """Build Page Maps from all snapshots using browser for AX tree."""
    _require_cli_deps()
    from tabulate import tabulate

    from pagemap.preprocessing.preprocess import count_tokens

    from .browser_session import BrowserSession
    from .page_map_builder import build_page_map_from_snapshot
    from .serializer import to_agent_prompt, to_json

    if snapshot_dir is None:
        # Default: project_root / data / snapshots
        snapshot_dir = Path(__file__).parent.parent.parent / "data" / "snapshots"
    snapshots_dir = snapshot_dir

    results = []
    async with BrowserSession() as session:
        for site_dir in sorted(snapshots_dir.iterdir()):
            if not site_dir.is_dir():
                continue
            for page_dir in sorted(site_dir.iterdir()):
                if not page_dir.is_dir():
                    continue
                if not (page_dir / "raw.html").exists():
                    continue

                site_id = site_dir.name
                page_id = page_dir.name

                try:
                    page_map = await build_page_map_from_snapshot(
                        session,
                        page_dir,
                        enable_tier3=False,
                    )

                    # Save
                    out_site = output_dir / site_id
                    out_site.mkdir(parents=True, exist_ok=True)

                    json_path = out_site / f"{page_id}.json"
                    json_path.write_text(to_json(page_map), encoding="utf-8")

                    prompt_path = out_site / f"{page_id}.txt"
                    prompt = to_agent_prompt(page_map, include_meta=True)
                    prompt_path.write_text(prompt, encoding="utf-8")

                    total_tokens = count_tokens(prompt)
                    results.append(
                        [
                            site_id,
                            page_id,
                            page_map.total_interactables,
                            page_map.pruned_tokens,
                            total_tokens,
                            f"{page_map.generation_ms:.0f}ms",
                        ]
                    )
                except Exception as e:
                    from .problem_details import sanitize_detail

                    safe_msg = sanitize_detail(str(e))
                    print(f"  ERROR {site_id}/{page_id}: {safe_msg}", file=sys.stderr)
                    results.append([site_id, page_id, "-", "-", "-", f"ERROR: {safe_msg}"])

    headers = ["Site", "Page", "Interactables", "Pruned Tok", "Total Tok", "Time"]
    print(tabulate(results, headers=headers, tablefmt="simple"))
    print(f"\nOutput: {output_dir}")


def _build_offline(output_dir: Path) -> None:
    """Build Page Maps offline (no browser, no interactables)."""
    _require_cli_deps()
    from tabulate import tabulate

    from pagemap.preprocessing.preprocess import count_tokens

    from .page_map_builder import build_page_map_offline
    from .serializer import to_agent_prompt, to_json

    snapshots_dir = Path(__file__).parent.parent.parent / "data" / "snapshots"

    # Domain → schema mapping
    domain_schema = {
        "coupang": "Product",
        "musinsa": "Product",
        "29cm": "Product",
        "kurly": "Product",
        # Phase 1: Fashion e-commerce
        "wconcept": "Product",
        "ssfshop": "Product",
        "handsome": "Product",
        "zara": "Product",
        "cos": "Product",
        "hm": "Product",
        "uniqlo": "Product",
        "nike": "Product",
        # Non-ecommerce
        "naver_news": "NewsArticle",
        "bbc_korean": "NewsArticle",
        "wikipedia_ko": "WikiArticle",
        "github": "SaaSPage",
        "govkr": "GovernmentPage",
    }

    results = []
    for site_dir in sorted(snapshots_dir.iterdir()):
        if not site_dir.is_dir():
            continue
        for page_dir in sorted(site_dir.iterdir()):
            if not page_dir.is_dir():
                continue

            raw_path = page_dir / "raw.html"
            meta_path = page_dir / "snapshot.json"
            if not raw_path.exists():
                continue

            site_id = site_dir.name
            page_id = page_dir.name
            raw_html = raw_path.read_text(encoding="utf-8")

            meta = {}
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))

            url = meta.get("url", f"file://{page_dir}")
            schema = domain_schema.get(site_id, "Product")

            try:
                page_map = build_page_map_offline(
                    raw_html=raw_html,
                    url=url,
                    site_id=site_id,
                    page_id=page_id,
                    schema_name=schema,
                )

                out_site = output_dir / site_id
                out_site.mkdir(parents=True, exist_ok=True)

                json_path = out_site / f"{page_id}.json"
                json_path.write_text(to_json(page_map), encoding="utf-8")

                prompt = to_agent_prompt(page_map, include_meta=True)
                prompt_path = out_site / f"{page_id}.txt"
                prompt_path.write_text(prompt, encoding="utf-8")

                total_tokens = count_tokens(prompt)
                results.append(
                    [
                        site_id,
                        page_id,
                        0,  # No interactables in offline mode
                        page_map.pruned_tokens,
                        total_tokens,
                        f"{page_map.generation_ms:.0f}ms",
                    ]
                )
            except Exception as e:
                from .problem_details import sanitize_detail

                safe_msg = sanitize_detail(str(e))
                print(f"  ERROR {site_id}/{page_id}: {safe_msg}", file=sys.stderr)
                results.append([site_id, page_id, "-", "-", "-", f"ERROR: {safe_msg}"])

    headers = ["Site", "Page", "Interactables", "Pruned Tok", "Total Tok", "Time"]
    print(tabulate(results, headers=headers, tablefmt="simple"))
    print(f"\nOutput: {output_dir}")


def cmd_auth(args: argparse.Namespace) -> None:
    """Authenticate with PageMap cloud."""
    from .cli_auth import login, logout, status

    if args.auth_command == "login":
        login()
    elif args.auth_command == "logout":
        logout()
    elif args.auth_command == "status":
        status()


def cmd_setup(args: argparse.Namespace) -> None:
    """Generate MCP config for a specific platform."""
    target = args.target
    _setup_mcp_config(target)


def _setup_mcp_config(target: str) -> None:
    """Write MCP server config for the given target platform."""
    from pathlib import Path

    home = Path.home()

    server_entry = {
        "command": "uvx",
        "args": ["retio-pagemap"],
    }

    # Platform-specific config paths and formats
    configs: dict[str, tuple[Path, str, str]] = {
        # (file_path, servers_key, description)
        "claude-code": (home / ".claude" / "mcp.json", "mcpServers", "Claude Code"),
        "cursor": (Path.cwd() / ".cursor" / "mcp.json", "mcpServers", "Cursor"),
        "windsurf": (Path.cwd() / ".windsurf" / "mcp.json", "mcpServers", "Windsurf"),
        "vscode": (Path.cwd() / ".vscode" / "mcp.json", "servers", "VS Code (Copilot)"),
        "claude-desktop": (
            (home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
            if sys.platform == "darwin"
            else (home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json")
            if sys.platform == "win32"
            else (home / ".config" / "claude" / "claude_desktop_config.json"),
            "mcpServers",
            "Claude Desktop",
        ),
    }

    if target not in configs:
        print(f"Unknown target: {target}", file=sys.stderr)
        print(f"Available: {', '.join(configs)}", file=sys.stderr)
        sys.exit(1)

    file_path, servers_key, display_name = configs[target]

    # Read existing config or create new
    existing: dict = {}
    if file_path.exists():
        try:
            existing = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Error: {file_path} contains invalid JSON. Fix it manually first.", file=sys.stderr)
            sys.exit(1)
        except OSError as exc:
            print(f"Error reading {file_path}: {exc}", file=sys.stderr)
            sys.exit(1)

    servers = existing.setdefault(servers_key, {})
    if "pagemap" in servers:
        print(f"PageMap already configured in {file_path}")
        return

    servers["pagemap"] = server_entry
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PageMap added to {display_name}: {file_path}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start MCP server, forwarding any extra args to the server."""
    from .server import main

    main(argv=getattr(args, "_server_argv", []))


def cmd_collect(args: argparse.Namespace) -> None:
    """Collect page snapshots for benchmarking."""
    if args.simulator:
        from ._internal.collect_sim import SimulatorController, collect_all_sim, collect_site_sim, load_config

        config = load_config()
        if args.all:
            collect_all_sim(config=config, count=args.count)
        elif args.site:
            controller = SimulatorController(config)
            # Ensure simulator is ready
            if not controller.get_booted_device_udid():
                controller.boot_device()
            controller.launch_app()
            if not controller.wait_for_ping():
                print("ERROR: App not responding. Is Retio DEBUG build installed?")
                sys.exit(1)

            page_types = [args.page_type] if args.page_type else None
            collect_site_sim(
                site_id=args.site,
                controller=controller,
                config=config,
                page_types=page_types,
                count=args.count,
            )
        else:
            print("Specify --site SITE or --all")
            sys.exit(1)
    else:
        from ._internal.collect import collect_all, collect_site

        if args.all:
            asyncio.run(collect_all(count=args.count))
        elif args.site:
            page_types = [args.page_type] if args.page_type else None
            asyncio.run(
                collect_site(
                    site_id=args.site,
                    page_types=page_types,
                    count=args.count,
                )
            )
        else:
            print("Specify --site SITE or --all")
            sys.exit(1)


def cmd_check_urls(args: argparse.Namespace) -> None:
    """Check health of all URLs in config.yaml."""
    from ._internal.check_urls import check_all_urls, save_report

    output_path = Path(args.output) if args.output else Path("url_health_report.json")
    report = check_all_urls(site_filter=args.site)

    s = report.summary
    print(f"\nURL Health Report ({report.checked_at})")
    print(f"  Total: {s.total}")
    print(f"  Valid: {s.valid}")
    print(f"  Expired: {s.expired}")
    print(f"  Blocked: {s.blocked}")
    print(f"  Dummy: {s.dummy}")
    print(f"  Redirect: {s.redirect}")

    save_report(report, output_path)
    print(f"\nReport saved to {output_path}")


def cmd_refresh_urls(args: argparse.Namespace) -> None:
    """Replace expired/dummy URLs with fresh ones."""
    from ._internal.refresh_urls import refresh_all_urls

    health_report = None
    if args.health_report:
        import json as _json

        _json.loads(Path(args.health_report).read_text(encoding="utf-8"))
        # Load from JSON is not directly supported — pass None to auto-detect
        health_report = None

    results = refresh_all_urls(
        health_report=health_report,
        dry_run=args.dry_run,
        site_filter=args.site,
        use_simulator=not args.no_simulator,
    )

    total_changes = sum(len(r.changes) for r in results)
    print(f"\nRefresh complete: {total_changes} URLs replaced across {len(results)} sites")
    for r in results:
        if r.changes:
            print(f"  {r.site_id}: {len(r.changes)} changes (from {r.listing_url_used[:60]})")
        elif r.skipped_reason:
            print(f"  {r.site_id}: skipped — {r.skipped_reason}")


def cmd_refresh_and_collect(args: argparse.Namespace) -> None:
    """Replace URLs and re-collect snapshots."""
    from ._internal.refresh_urls import refresh_and_collect

    results = refresh_and_collect(site_filter=args.site)

    total_changes = sum(len(r.changes) for r in results)
    print(f"\nRefresh & collect complete: {total_changes} URLs replaced and re-collected")
    for r in results:
        if r.changes:
            print(f"  {r.site_id}: {len(r.changes)} changes")


def cmd_convert(args: argparse.Namespace) -> None:
    """Convert snapshots using competitor tools."""
    from ._internal.benchmark.converters import CONVERTERS, convert_all_pages

    # Determine snapshot directory
    snapshot_dir = Path(args.snapshot_dir) if args.snapshot_dir else None
    if snapshot_dir is None:
        # Default: retio project snapshots (sibling project)
        default_snap = Path(__file__).parent.parent.parent.parent / "data" / "snapshots"
        if default_snap.exists():
            snapshot_dir = default_snap
        else:
            print("ERROR: Snapshot directory not found. Use --snapshot-dir to specify.")
            sys.exit(1)

    # Determine tools
    if args.tool == "all":
        tools = list(CONVERTERS.keys())
    else:
        tools = [args.tool]

    # Determine output directory
    output_dir, _ = _validate_output_path(args.output)

    print(f"Converting with tools: {tools}")
    print(f"Snapshot dir: {snapshot_dir}")
    if args.pilot:
        print(f"Pilot mode: {args.pilot_count} pages per site")

    results = asyncio.run(
        convert_all_pages(
            snapshot_dir=snapshot_dir,
            output_dir=output_dir,
            tools=tools,
            force=args.force,
            pilot=args.pilot,
            pilot_count=args.pilot_count,
        )
    )

    # Summary
    for tool_name, tool_results in results.items():
        success = sum(1 for r in tool_results if r.status == "success")
        errors = sum(1 for r in tool_results if r.status == "error")
        print(f"\n{tool_name}: {success} success, {errors} errors")
        if tool_results:
            avg_tokens = sum(r.token_count for r in tool_results if r.status == "success")
            count = max(1, success)
            print(f"  Avg tokens: {avg_tokens // count:,}")


def cmd_benchmark(args: argparse.Namespace) -> None:
    """Run benchmark."""
    data_dir = Path(__file__).parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if args.sim_static:
        _run_sim_benchmark(args, data_dir, mode="sim_static")
    elif args.sim_live:
        _run_sim_benchmark(args, data_dir, mode="sim_live")
    elif args.live:
        _run_live_benchmark(args, data_dir)
    else:
        _run_static_benchmark(args, data_dir)


def _run_static_benchmark(args: argparse.Namespace, data_dir: Path) -> None:
    """Run static benchmark (multi-condition comparison)."""
    from ._internal.benchmark.converters import load_converted_pages
    from ._internal.benchmark.report import (
        generate_full_report,
        load_static_results,
        save_results_json,
    )
    from ._internal.benchmark.runner import (
        ALL_CONDITIONS,
        BASE_CONDITIONS,
        COMPETITOR_CONDITIONS,
        load_tasks,
        run_static_benchmark,
    )

    result_path = data_dir / "benchmark_results.json"
    report_path = data_dir / "benchmark_report.md"
    tasks = load_tasks(mode="static")
    force = getattr(args, "force", False)
    task_filter = getattr(args, "task", None)

    # Determine conditions
    conditions_arg = getattr(args, "conditions", None)
    if conditions_arg == "all":
        conditions = list(ALL_CONDITIONS)
    elif conditions_arg:
        conditions = [c.strip() for c in conditions_arg.split(",")]
    else:
        conditions = list(BASE_CONDITIONS)

    # Filter tasks if --task specified
    if task_filter:
        tasks = [t for t in tasks if t["id"] == task_filter]
        if not tasks:
            print(f"Task '{task_filter}' not found in static tasks.")
            sys.exit(1)

    # Pre-flight: load existing results for dedup
    existing = []
    if not force and result_path.exists():
        existing = load_static_results(result_path)
        existing_pairs = {(r.task_id, r.condition) for r in existing}
        print(f"Existing results: {len(existing_pairs)} (task, condition) pairs")

        requested_set = set(conditions)
        task_ids = {t["id"] for t in tasks}
        needed_pairs = {(tid, c) for tid in task_ids for c in requested_set}
        if needed_pairs.issubset(existing_pairs):
            print(f"All {len(needed_pairs)} pairs completed. Use --force to re-run.")
            from ._internal.benchmark.runner import BenchmarkResult

            result = BenchmarkResult(task_results=existing, conditions=conditions)
            _benchmark_postflight(
                result,
                tasks,
                generate_full_report,
                save_results_json,
                result_path,
                report_path,
            )
            return

    # Load PageMap agent prompt files
    # PageMap .txt files live under the project-root data/ directory,
    # NOT under src/pagemap/data/ (which holds benchmark results/reports).
    page_maps: dict[str, str] = {}
    pm_data_dir = Path(__file__).parent.parent.parent / "data"
    for txt_file in pm_data_dir.rglob("*.txt"):
        site_id = txt_file.parent.name
        page_id = txt_file.stem
        page_maps[f"{site_id}/{page_id}"] = txt_file.read_text(encoding="utf-8")

    # Load converted pages for competitor conditions
    converted_pages: dict[str, dict[str, str]] | None = None
    competitor_conds = set(conditions) & set(COMPETITOR_CONDITIONS)
    if competitor_conds:
        converted_pages = load_converted_pages()
        loaded_tools = list(converted_pages.keys()) if converted_pages else []
        print(f"Loaded converted pages for: {loaded_tools}")

    print(f"Running {len(tasks)} static tasks with {len(page_maps)} page maps...")
    print(f"Conditions: {conditions}")
    result = asyncio.run(
        run_static_benchmark(
            tasks=tasks,
            page_maps=page_maps,
            existing_results=existing if existing else None,
            save_path=result_path,
            converted_pages=converted_pages,
            conditions=conditions,
        )
    )

    _benchmark_postflight(
        result,
        tasks,
        generate_full_report,
        save_results_json,
        result_path,
        report_path,
    )


def _run_live_benchmark(args: argparse.Namespace, data_dir: Path) -> None:
    """Run live benchmark (multi-turn agentic loop)."""
    from ._internal.benchmark.report import (
        generate_combined_judgment,
        generate_live_report,
        load_live_results,
        save_live_results_json,
    )
    from ._internal.benchmark.runner import LiveBenchmarkResult, load_tasks, run_live_benchmark

    result_path = data_dir / "live_benchmark_results.json"
    report_path = data_dir / "live_benchmark_report.md"
    tasks = load_tasks(mode="live")
    force = getattr(args, "force", False)

    # Pre-flight: load existing results for dedup
    existing = []
    if not force and result_path.exists():
        existing = load_live_results(result_path)
        succeeded = {r.task_id for r in existing if r.answer and not r.error}
        print(f"Existing results: {len(succeeded)}/{len(tasks)} tasks completed")
        if len(succeeded) >= len(tasks):
            print(f"All {len(tasks)} tasks completed. Use --force to re-run.")
            result = LiveBenchmarkResult(task_results=existing)
            _benchmark_postflight(
                result,
                tasks,
                generate_live_report,
                save_live_results_json,
                result_path,
                report_path,
            )
            return

    print(f"Running {len(tasks)} live tasks...\n")

    result = asyncio.run(
        run_live_benchmark(
            tasks=tasks,
            existing_results=existing if existing else None,
            save_path=result_path,
        )
    )

    report = _benchmark_postflight(
        result,
        tasks,
        generate_live_report,
        save_live_results_json,
        result_path,
        report_path,
    )

    # Combined judgment (use static results if available)
    static_results_path = data_dir / "benchmark_results.json"
    static_rate = 0.0
    if static_results_path.exists():
        static_data = json.loads(static_results_path.read_text())
        pm_agg = static_data.get("aggregate", {}).get("page_map", {})
        static_rate = pm_agg.get("success_rate", 0.0)
        print(f"(Using static benchmark result: {static_rate:.1%})")

    judgment = generate_combined_judgment(static_rate, result)
    print("\n" + judgment)
    # Append judgment to report file
    report_path.write_text(report + "\n" + judgment)


def _run_sim_benchmark(args: argparse.Namespace, data_dir: Path, mode: str) -> None:
    """Run simulator-based benchmark (sim_live or sim_static)."""
    from ._internal.benchmark.report import (
        generate_live_report,
        load_live_results,
        save_live_results_json,
    )
    from ._internal.benchmark.runner import LiveBenchmarkResult, load_tasks

    result_path = data_dir / f"{mode}_benchmark_results.json"
    task_id = getattr(args, "task", None)
    model = getattr(args, "model", "claude-sonnet-4-5-20250929")
    force = getattr(args, "force", False)

    tasks = load_tasks(mode=mode)

    # Pre-flight: load existing results for dedup
    existing = []
    if not force and result_path.exists():
        existing = load_live_results(result_path)
        succeeded = {r.task_id for r in existing if r.answer and not r.error}
        target_tasks = [t for t in tasks if t["id"] == task_id] if task_id else tasks
        total = len(target_tasks)
        print(f"Existing results: {len(succeeded)}/{total} tasks completed")
        if len(succeeded) >= total:
            print(f"All {total} tasks completed. Use --force to re-run.")
            result = LiveBenchmarkResult(task_results=existing)
            _benchmark_postflight(
                result,
                tasks,
                generate_live_report,
                save_live_results_json,
                result_path,
                data_dir / f"{mode}_benchmark_report.md",
            )
            return

    if task_id:
        print(f"Running single {mode} task: {task_id}")
    else:
        print(f"Running {len(tasks)} {mode} tasks...\n")

    runner_kwargs = dict(
        tasks=tasks,
        task_id=task_id,
        model=model,
        existing_results=existing if existing else None,
        save_path=result_path,
    )

    if mode == "sim_live":
        from ._internal.benchmark.runner import run_sim_live_benchmark

        result = run_sim_live_benchmark(**runner_kwargs)
    else:
        from ._internal.benchmark.runner import run_sim_static_benchmark

        result = asyncio.run(run_sim_static_benchmark(**runner_kwargs))

    _benchmark_postflight(
        result,
        tasks,
        generate_live_report,
        save_live_results_json,
        result_path,
        data_dir / f"{mode}_benchmark_report.md",
    )


def _get_server_options_help() -> str:
    """Extract server option help text from _parse_server_args.

    Lazily imports server module only when serve --help is requested.
    """
    import io
    from contextlib import redirect_stdout

    from .server import _parse_server_args

    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            _parse_server_args(["--help"])
    except SystemExit:
        pass

    raw = buf.getvalue()
    # Extract lines after options header, skipping -h/--help entry
    lines = raw.splitlines()
    start = None
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped in ("options:", "optional arguments:"):
            start = i + 1
            break
    if start is None:
        return raw

    result: list[str] = []
    skip_h = False
    for line in lines[start:]:
        stripped = line.lstrip()
        if stripped.startswith("-h,") or stripped.startswith("-h ") or stripped == "-h":
            skip_h = True
            continue
        if skip_h:
            if stripped.startswith("--") or stripped == "":
                skip_h = False
            else:
                continue
        result.append(line)
    return "\n".join(result).strip("\n")


class _ServeHelpAction(argparse.Action):
    """Custom help action for 'serve' that appends dynamic server options."""

    def __init__(
        self,
        option_strings,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        help=None,
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        parser.print_help()
        try:
            server_opts = _get_server_options_help()
            if server_opts:
                print(f"\nforwarded server options:\n{server_opts}")
        except (ImportError, AttributeError, TypeError) as exc:
            logging.debug("ServeHelpAction fallback: %s", exc)
            print(
                "\n(could not load server options — run 'pagemap serve' to check dependencies)",
                file=sys.stderr,
            )
        parser.exit()


def cmd_openapi(args: argparse.Namespace) -> None:
    """Generate OpenAPI 3.1 specification."""
    from .openapi import generate_openapi_spec, spec_to_json, spec_to_yaml
    from .server import mcp

    spec = generate_openapi_spec(mcp)

    if args.format == "yaml":
        output = spec_to_yaml(spec)
    else:
        output = spec_to_json(spec)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"OpenAPI spec written to {args.output}", file=sys.stderr)
    else:
        print(output)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Page Map CLI",
        prog="python -m pagemap.cli",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Always available
    _build_epilog = """\
examples:
  %(prog)s --url https://example.com               Build from live URL
  %(prog)s --url https://example.com --format json  Output JSON to stdout
  %(prog)s --url https://example.com -o result.json Save to single file
  %(prog)s --url https://example.com -o out/        Save to directory
  %(prog)s --snapshots                              Build from all snapshots
"""
    p_build = subparsers.add_parser(
        "build",
        help="Build Page Maps from URLs or snapshots",
        epilog=_build_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_build.add_argument("--url", type=str, metavar="URL", help="Target URL to build Page Map from")
    p_build.add_argument("--snapshots", action="store_true", help="Build from snapshots with browser")
    p_build.add_argument("--snapshot-dir", type=str, metavar="DIR", help="Snapshot directory (default: data/snapshots)")
    p_build.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="PATH",
        help="Output path: file (out.json) or directory (out/)",
    )
    p_build.add_argument(
        "--format",
        type=str,
        choices=["json", "text", "markdown"],
        help="Output format to stdout (mutually exclusive with --output)",
    )

    p_serve = subparsers.add_parser(
        "serve",
        help="Start MCP server (extra args forwarded to server)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s                                Start with stdio transport (default)
  %(prog)s --transport http --port 8000   Start HTTP server on port 8000
  %(prog)s --allow-local                  Allow localhost/private IP access""",
        add_help=False,
    )
    p_serve.add_argument(
        "-h",
        "--help",
        action=_ServeHelpAction,
        default=argparse.SUPPRESS,
        help="show this help message and exit",
    )

    # OpenAPI spec generation
    _openapi_epilog = """\
examples:
  %(prog)s                                 Print JSON to stdout
  %(prog)s --format yaml                   Print YAML to stdout
  %(prog)s -o openapi.json                 Save to file
  %(prog)s --format yaml -o openapi.yaml   Save YAML to file
"""
    p_openapi = subparsers.add_parser(
        "openapi",
        help="Generate OpenAPI 3.1 specification",
        epilog=_openapi_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_openapi.add_argument(
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Output format (default: json)",
    )
    p_openapi.add_argument(
        "-o",
        "--output",
        type=str,
        metavar="PATH",
        help="Output file path (default: stdout)",
    )

    # try — zero-config demo
    _try_epilog = """\
examples:
  %(prog)s https://example.com                 Print PageMap to stdout
  %(prog)s https://amazon.com --format json    Output as JSON
  %(prog)s https://news.ycombinator.com        Works with any site
"""
    p_try = subparsers.add_parser(
        "try",
        help="Try PageMap on any URL (no config needed)",
        epilog=_try_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_try.add_argument("url", type=str, help="URL to analyze")
    p_try.add_argument(
        "--format",
        type=str,
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )

    # setup — MCP config generation
    _setup_targets = ["claude-code", "cursor", "windsurf", "vscode", "claude-desktop"]
    _setup_epilog = """\
examples:
  %(prog)s claude-code      Add to ~/.claude/mcp.json
  %(prog)s cursor            Add to .cursor/mcp.json
  %(prog)s vscode            Add to .vscode/mcp.json
  %(prog)s claude-desktop    Add to Claude Desktop config
"""
    p_setup = subparsers.add_parser(
        "setup",
        help="Add PageMap MCP server to your editor/agent",
        epilog=_setup_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_setup.add_argument(
        "target",
        type=str,
        choices=_setup_targets,
        help="Target platform",
    )

    # auth — OAuth login/logout/status
    p_auth = subparsers.add_parser(
        "auth",
        help="Authenticate with PageMap cloud (login/logout/status)",
    )
    auth_sub = p_auth.add_subparsers(dest="auth_command", required=True)
    auth_sub.add_parser("login", help="Log in and save API key")
    auth_sub.add_parser("logout", help="Remove stored credentials")
    auth_sub.add_parser("status", help="Show current auth status")

    commands = {
        "build": cmd_build,
        "serve": cmd_serve,
        "openapi": cmd_openapi,
        "try": cmd_try,
        "setup": cmd_setup,
        "auth": cmd_auth,
    }

    # ── Web fetch / search ────────────────────────────────────────
    _search_epilog = """\
examples:
  %(prog)s "python type hints"                       Search DuckDuckGo and print results
  %(prog)s "rust async" --max-results 5 --format json
  %(prog)s "react 19 docs" --session new:docs       Use a named session for continuity"""

    p_search = subparsers.add_parser(
        "search",
        help="Web search (DuckDuckGo, Brave, Bing, Google, SearXNG, Exa, Tavily, Firecrawl)",
        epilog=_search_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_search.add_argument("query", type=str, help="Search query")
    p_search.add_argument(
        "--provider",
        type=str,
        default="duckduckgo",
        help="Search provider (default: duckduckgo)",
    )
    p_search.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Maximum results (1-20, default 10)",
    )
    p_search.add_argument(
        "--recency",
        type=str,
        choices=["day", "week", "month", "year"],
        default=None,
        help="Time-bucket hint (provider-dependent)",
    )
    p_search.add_argument(
        "--domain",
        action="append",
        default=None,
        help="Domain filter (repeatable; prefix with '-' to exclude)",
    )
    p_search.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session id; 'new' creates a fresh one, 'new:<name>' names it",
    )
    p_search.add_argument(
        "--use-browser",
        action="store_true",
        help="Render the search engine page through CloakBrowser (more natural footprint)",
    )
    p_search.add_argument(
        "--format",
        type=str,
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    commands["search"] = cmd_search

    _fetch_epilog = """\
examples:
  %(prog)s https://example.com                         Print extracted markdown to stdout
  %(prog)s https://example.com --format text           Plain text output
  %(prog)s https://example.com --format json -o out.json
  %(prog)s https://example.com --session new:docs      Reuse a named session"""

    p_fetch = subparsers.add_parser(
        "fetch",
        help="Fetch a URL and extract content (markdown|text|html|json)",
        epilog=_fetch_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_fetch.add_argument("url", type=str, help="URL to fetch")
    p_fetch.add_argument(
        "--mode",
        type=str,
        choices=["browser", "fast"],
        default="browser",
        help="Fetch mode (default: browser)",
    )
    p_fetch.add_argument(
        "--format",
        type=str,
        choices=["markdown", "text", "html", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    p_fetch.add_argument(
        "--max-chars",
        type=int,
        default=50_000,
        help="Truncation limit (default 50000)",
    )
    p_fetch.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session id; 'new' creates a fresh one, 'new:<name>' names it",
    )
    p_fetch.add_argument(
        "--format-output",
        type=str,
        choices=["auto", "json"],
        default="auto",
        help="Wrap result as JSON instead of content (default: auto)",
    )
    commands["fetch"] = cmd_fetch

    p_batch_fetch = subparsers.add_parser(
        "batch-fetch",
        help="Fetch multiple URLs in parallel",
    )
    p_batch_fetch.add_argument("urls", nargs="+", help="URLs to fetch")
    p_batch_fetch.add_argument(
        "--mode",
        type=str,
        choices=["browser", "fast"],
        default="browser",
    )
    p_batch_fetch.add_argument(
        "--format",
        type=str,
        choices=["markdown", "text", "html"],
        default="markdown",
    )
    p_batch_fetch.add_argument(
        "--max-chars",
        type=int,
        default=50_000,
    )
    p_batch_fetch.add_argument(
        "--max-concurrency",
        type=int,
        default=5,
    )
    p_batch_fetch.add_argument(
        "--session",
        type=str,
        default=None,
    )
    p_batch_fetch.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output directory (one file per URL)",
    )
    p_batch_fetch.add_argument(
        "--format-output",
        type=str,
        choices=["auto", "json"],
        default="auto",
    )
    commands["batch-fetch"] = cmd_batch_fetch

    p_sessions = subparsers.add_parser(
        "sessions",
        help="Manage web sessions (list, close)",
    )
    p_sessions_sub = p_sessions.add_subparsers(dest="sessions_command", required=True)
    p_sessions_list = p_sessions_sub.add_parser("list", help="List active web sessions")
    p_sessions_list.add_argument(
        "--format", type=str, choices=["text", "json"], default="text"
    )
    p_sessions_close = p_sessions_sub.add_parser("close", help="Close a web session")
    p_sessions_close.add_argument(
        "session_id",
        type=str,
        nargs="?",
        default="default",
        help="Session id to close (default: reset the default session)",
    )
    commands["sessions"] = cmd_sessions

    # ── Credits management (S8) ─────────────────────────────────
    if _has_management_db():
        p_credits = subparsers.add_parser(
            "credits",
            help="Manage credits (requires SUPABASE_DB_URL)",
        )
        credits_sub = p_credits.add_subparsers(dest="credits_command", required=True)

        credits_sub.add_parser("balance", help="Show credit balance")

        p_topup = credits_sub.add_parser("topup", help="Create a checkout for credit top-up")
        p_topup.add_argument("--price-id", type=str, default="pri_starter", help="Paddle price ID")
        p_topup.add_argument("--open", action="store_true", help="Open checkout URL in browser")

        commands["credits"] = cmd_credits

        # keys management
        p_keys = subparsers.add_parser("keys", help="Manage API keys")
        keys_sub = p_keys.add_subparsers(dest="keys_command", required=True)
        keys_sub.add_parser("list", help="List all API keys")
        p_kc = keys_sub.add_parser("create", help="Create a new API key")
        p_kc.add_argument("--label", default="api-key")
        p_kc.add_argument("--expires-in-days", type=int)
        p_kr = keys_sub.add_parser("revoke", help="Revoke an API key")
        p_kr.add_argument("key_hash")
        p_krot = keys_sub.add_parser("rotate", help="Rotate (create new + revoke old)")
        p_krot.add_argument("key_hash")
        p_krot.add_argument("--label", default="api-key-rotated")
        commands["keys"] = cmd_keys

        # usage statistics
        p_usage = subparsers.add_parser("usage", help="Show usage statistics")
        p_usage.add_argument("--period", type=str, help="Time period: 7d, 24h, 30d")
        commands["usage"] = cmd_usage

        # user info
        subparsers.add_parser("user", help="Show user info")
        commands["user"] = cmd_user

    # Development-only: internal tools
    if _has_internal():
        p_build.add_argument("--offline", action="store_true", help=argparse.SUPPRESS)

        p_validate = subparsers.add_parser("validate", help="Run AX Tree validation")
        p_validate.add_argument("--url", type=str)
        p_validate.add_argument("--all", action="store_true")
        p_validate.add_argument("--save", type=str)

        p_collect = subparsers.add_parser("collect", help="Collect page snapshots")
        p_collect.add_argument("--site", type=str, help="Site ID (e.g., musinsa, zara)")
        p_collect.add_argument(
            "--type", type=str, dest="page_type", help="Page type (product_detail, search_results, listing)"
        )
        p_collect.add_argument("--count", type=int, default=3, help="Pages per type (default: 3)")
        p_collect.add_argument("--all", action="store_true", help="Collect all sites")
        p_collect.add_argument("--simulator", action="store_true", help="Use iOS Simulator instead of Playwright")

        commands["validate"] = cmd_validate
        commands["collect"] = cmd_collect

        p_check_urls = subparsers.add_parser("check-urls", help="Check health of all URLs in config")
        p_check_urls.add_argument("--site", type=str, help="Only check this site")
        p_check_urls.add_argument("--output", type=str, help="Output JSON path (default: url_health_report.json)")

        p_refresh_urls = subparsers.add_parser("refresh-urls", help="Replace expired/dummy URLs")
        p_refresh_urls.add_argument("--site", type=str, help="Only refresh this site")
        p_refresh_urls.add_argument("--dry-run", action="store_true", help="Preview changes without modifying config")
        p_refresh_urls.add_argument("--health-report", type=str, help="Path to health report JSON")
        p_refresh_urls.add_argument("--no-simulator", action="store_true", help="Skip simulator, use snapshot fallback")

        p_refresh_collect = subparsers.add_parser("refresh-and-collect", help="Replace URLs and re-collect snapshots")
        p_refresh_collect.add_argument("--site", type=str, help="Only refresh this site")
        p_refresh_collect.add_argument("--health-report", type=str, help="Path to health report JSON")

        commands["check-urls"] = cmd_check_urls
        commands["refresh-urls"] = cmd_refresh_urls
        commands["refresh-and-collect"] = cmd_refresh_and_collect

    # Development-only: benchmark tools
    if _has_benchmark():
        from ._internal.benchmark.converters import CONVERTERS
        from ._internal.benchmark.runner import ALL_CONDITIONS

        p_convert = subparsers.add_parser("convert", help="Convert snapshots with competitor tools")
        p_convert.add_argument(
            "--tool",
            type=str,
            default="all",
            choices=list(CONVERTERS.keys()) + ["all"],
            help="Converter tool to use (default: all)",
        )
        p_convert.add_argument("--snapshot-dir", type=str, help="Path to snapshot directory")
        p_convert.add_argument("--output", type=str, help="Output directory for converted files")
        p_convert.add_argument("--force", action="store_true", help="Re-convert even if already done")
        p_convert.add_argument("--pilot", action="store_true", help="Convert only a few pages per site (cost check)")
        p_convert.add_argument("--pilot-count", type=int, default=3, help="Pages per site in pilot mode (default: 3)")

        p_bench = subparsers.add_parser("benchmark", help="Run benchmark")
        p_bench.add_argument("--static", action="store_true")
        p_bench.add_argument("--live", action="store_true")
        p_bench.add_argument(
            "--sim-live", action="store_true", help="Run simulator-based shopping simulation benchmark"
        )
        p_bench.add_argument(
            "--sim-static", action="store_true", help="Run static benchmark on iOS Simulator collected data"
        )
        p_bench.add_argument("--task", type=str, help="Run only a specific task ID (e.g., SC_MU_01)")
        p_bench.add_argument("--model", type=str, default="claude-sonnet-4-5-20250929", help="Claude model to use")
        p_bench.add_argument("--force", action="store_true", help="Ignore existing results and re-run all tasks")
        p_bench.add_argument(
            "--conditions",
            type=str,
            default=None,
            help=f"Conditions to run: comma-separated list or 'all'. Options: {', '.join(ALL_CONDITIONS)}",
        )

        commands["convert"] = cmd_convert
        commands["benchmark"] = cmd_benchmark

    args, remaining = parser.parse_known_args()

    # Forward remaining args to server when using 'serve' command
    if args.command == "serve":
        args._server_argv = remaining
    elif remaining:
        parser.error(f"unrecognized arguments: {' '.join(remaining)}")

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        from .problem_details import from_exception

        problem = from_exception(e, tool_context="cli")
        print(problem.to_cli_text(), file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
