from __future__ import annotations

import argparse
import os
import shutil
import sys


def _check_prerequisites() -> None:
    errors = []

    if not os.environ.get("OPENROUTER_API_KEY"):
        errors.append(
            "OPENROUTER_API_KEY is not set.\n"
            "  Export it:  export OPENROUTER_API_KEY=sk-or-...\n"
            "  Or copy .env.example to .env and source it."
        )

    for tool, install_hint in [
        ("git", "Install git: https://git-scm.com"),
        ("go", "Install Go 1.21+: https://go.dev/dl/"),
        ("rg", "Install ripgrep: brew install ripgrep / apt install ripgrep"),
    ]:
        if shutil.which(tool) is None:
            errors.append(f"'{tool}' not found on PATH. {install_hint}")

    if errors:
        print("ERROR: Missing prerequisites:\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}\n", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Agentic AI contributor for open-source Go projects",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run subcommand
    run_parser = subparsers.add_parser("run", help="Solve a GitHub issue")
    run_parser.add_argument("--repo", required=True, help="GitHub repo (owner/name)")
    run_parser.add_argument("--issue", required=True, type=int, help="Issue number")
    run_parser.add_argument("--base-commit", help="Base commit SHA to checkout")
    run_parser.add_argument("--max-iterations", type=int, default=None, help="Max agent iterations (default: 6)")
    run_parser.add_argument("--model", default=None, help="Model ID (OpenRouter format, e.g. anthropic/claude-sonnet-4-5)")

    # compare subcommand
    cmp_parser = subparsers.add_parser("compare", help="Compare agent output to accepted PR")
    cmp_parser.add_argument("--repo", required=True, help="GitHub repo (owner/name)")
    cmp_parser.add_argument("--issue", required=True, type=int, help="Issue number")
    cmp_parser.add_argument("--pr", required=True, type=int, help="Merged PR number")
    cmp_parser.add_argument("--model", default=None, help="Model ID (OpenRouter format, e.g. anthropic/claude-sonnet-4-5)")

    args = parser.parse_args()

    _check_prerequisites()

    from agent.config import build_config

    config = build_config(args)

    if args.command == "run":
        from agent.loop import run_agent

        summary = run_agent(config)
        status = "PASSED" if summary.validation_passed else "FAILED"
        if summary.error:
            status = f"ERROR: {summary.error}"
        print(f"\nResult: {status}")
        print(f"Output: {config.output_dir}/")
        sys.exit(0 if summary.validation_passed else 1)

    elif args.command == "compare":
        from agent.compare import run_compare

        run_compare(config, args.pr)


if __name__ == "__main__":
    main()
