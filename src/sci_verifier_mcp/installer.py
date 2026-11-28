"""Universal agent installer and configuration generator for all AI coding agents."""

import contextlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REMOTE_UVX_COMMAND = "uvx"
REMOTE_UVX_ARGS = ["--from", "git+https://github.com/rishibagale/sci_verifier_mcp.git", "sci-verifier-mcp"]

AUTO_APPROVE_TOOLS = [
    "check_equation_equivalence",
    "check_dimensional_analysis",
    "check_smt_claim",
    "verify_ode_pde_solution",
    "check_limiting_cases",
    "verify_simulation_invariants",
    "search_lean_premises",
    "validate_crystal_structure",
    "check_stoichiometry_and_valence",
    "check_elastic_and_phonon_stability",
    "verify_citation",
    "verify_claim_against_paper",
    "find_similar_papers",
    "track_recent_discoveries",
    "export_audit_certificate",
]


def get_repo_root() -> Path:
    """Get the root directory of the repository."""
    return Path(__file__).resolve().parent.parent.parent


def get_command_and_args(mode: str = "local") -> tuple[str, list[str]]:
    """Determine the command and arguments based on execution mode."""
    if mode.lower() == "uvx":
        return REMOTE_UVX_COMMAND, list(REMOTE_UVX_ARGS)

    # Local mode: prefer uv run or current python interpreter
    repo_root = get_repo_root()
    uv_bin = shutil.which("uv")
    if uv_bin:
        return "uv", ["--directory", str(repo_root), "run", "sci-verifier-mcp"]

    # Fallback to current virtualenv python
    py_exe = sys.executable
    return py_exe, ["-m", "sci_verifier_mcp.server"]


def get_client_config_paths() -> dict[str, list[Path]]:
    """Map client identifiers to possible configuration paths across operating systems."""
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))

    return {
        "cline": [
            appdata / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
            home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
            home / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
            get_repo_root() / ".cline" / "mcp.json",
        ],
        "roo": [
            appdata / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
            home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
            home / ".config" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
        ],
        "cursor": [
            home / ".cursor" / "mcp.json",
            get_repo_root() / ".cursor" / "mcp.json",
        ],
        "windsurf": [
            home / ".codeium" / "windsurf" / "mcp_config.json",
        ],
        "opencode": [
            home / ".config" / "opencode" / "mcp.json",
            get_repo_root() / "opencode.json",
        ],
        "claude": [
            appdata / "Claude" / "claude_desktop_config.json",
            home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
            home / ".config" / "Claude" / "claude_desktop_config.json",
        ],
        "zed": [
            appdata / "Zed" / "settings.json",
            home / "Library" / "Application Support" / "Zed" / "settings.json",
            home / ".config" / "zed" / "settings.json",
            get_repo_root() / ".zed" / "settings.json",
        ],
        "continue": [
            home / ".continue" / "config.json",
        ],
    }


def generate_snippet_for_client(client_name: str, mode: str = "local") -> dict[str, Any]:
    """Generate configuration dictionary structure for a given client."""
    cmd, args = get_command_and_args(mode=mode)
    cname = client_name.lower()

    if cname in ("cline", "roo"):
        return {
            "command": cmd,
            "args": args,
            "env": {
                "MP_API_KEY": os.getenv("MP_API_KEY", ""),
                "CROSSREF_MAILTO": os.getenv("CROSSREF_MAILTO", "sci-verifier@example.com"),
            },
            "disabled": False,
            "autoApprove": AUTO_APPROVE_TOOLS,
        }

    elif cname == "zed":
        return {
            "command": {
                "path": cmd,
                "args": args,
                "env": {
                    "MP_API_KEY": os.getenv("MP_API_KEY", ""),
                },
            }
        }

    elif cname == "continue":
        return {
            "name": "sci-verifier",
            "command": cmd,
            "args": args,
            "env": {
                "MP_API_KEY": os.getenv("MP_API_KEY", ""),
            },
        }

    # Standard MCP server dictionary (Cursor, Windsurf, OpenCode, Claude Desktop)
    return {
        "command": cmd,
        "args": args,
        "env": {
            "MP_API_KEY": os.getenv("MP_API_KEY", ""),
            "CROSSREF_MAILTO": os.getenv("CROSSREF_MAILTO", "sci-verifier@example.com"),
        },
    }


def merge_config_into_file(file_path: Path, client_name: str, mode: str = "local") -> tuple[bool, str]:
    """Safely merge SciVerifier into an existing or new client JSON configuration file."""
    cname = client_name.lower()
    snippet = generate_snippet_for_client(cname, mode=mode)

    existing_data: dict[str, Any] = {}
    if file_path.exists():
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if content:
                existing_data = json.loads(content)
        except Exception as e:
            return False, f"Could not parse existing JSON in {file_path}: {e}"

        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        with contextlib.suppress(Exception):
            shutil.copy2(file_path, backup_path)

    # Merge based on schema
    if cname in ("cline", "roo", "cursor", "windsurf", "claude"):
        if "mcpServers" not in existing_data or not isinstance(existing_data["mcpServers"], dict):
            existing_data["mcpServers"] = {}
        existing_data["mcpServers"]["sci-verifier"] = snippet

    elif cname == "opencode":
        if "mcp" in existing_data and isinstance(existing_data["mcp"], dict):
            if "servers" not in existing_data["mcp"] or not isinstance(existing_data["mcp"]["servers"], dict):
                existing_data["mcp"]["servers"] = {}
            existing_data["mcp"]["servers"]["sci-verifier"] = snippet
        else:
            if "mcpServers" not in existing_data or not isinstance(existing_data["mcpServers"], dict):
                existing_data["mcpServers"] = {}
            existing_data["mcpServers"]["sci-verifier"] = snippet

    elif cname == "zed":
        if "context_servers" not in existing_data or not isinstance(existing_data["context_servers"], dict):
            existing_data["context_servers"] = {}
        existing_data["context_servers"]["sci-verifier"] = snippet

    elif cname == "continue":
        servers = existing_data.get("mcpServers", [])
        if isinstance(servers, list):
            # Replace existing or append
            filtered = [s for s in servers if isinstance(s, dict) and s.get("name") != "sci-verifier"]
            filtered.append(snippet)
            existing_data["mcpServers"] = filtered
        elif isinstance(servers, dict):
            servers["sci-verifier"] = snippet
            existing_data["mcpServers"] = servers
        else:
            existing_data["mcpServers"] = [snippet]

    # Write merged configuration
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
        return True, f"Successfully configured {client_name} in {file_path}"
    except Exception as e:
        return False, f"Failed to write configuration to {file_path}: {e}"


def detect_installed_clients() -> dict[str, Path]:
    """Scan the system and return all detected client configuration files."""
    paths_map = get_client_config_paths()
    detected = {}

    for client, paths in paths_map.items():
        for p in paths:
            if p.exists() or (p.parent.exists() and not str(p).startswith(str(get_repo_root()))):
                detected[client] = p
                break

    return detected


def run_installer_cli(args: list[str] | None = None) -> int:
    """Main CLI entrypoint for installing or viewing client configurations."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="sci-verifier-mcp install",
        description="Connect SciVerifier MCP to all coding agents, editors, and IDEs."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Automatically detect and configure all installed agents on this machine."
    )
    parser.add_argument(
        "--target",
        choices=["cline", "roo", "cursor", "windsurf", "opencode", "claude", "zed", "continue"],
        help="Configure a specific agent or IDE."
    )
    parser.add_argument(
        "--mode",
        choices=["local", "uvx"],
        default="local",
        help="Command execution mode: 'local' (virtualenv/uv run) or 'uvx' (remote zero-install)."
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print the JSON configuration snippet to stdout without writing files."
    )

    parsed = parser.parse_args(args)

    if parsed.print_only:
        targets = [parsed.target] if parsed.target else ["cline", "cursor", "opencode", "claude", "zed"]
        output = {}
        for t in targets:
            output[t] = generate_snippet_for_client(t, mode=parsed.mode)
        print(json.dumps(output, indent=2))
        return 0

    if parsed.target:
        # Install to target client
        paths_map = get_client_config_paths()
        target_paths = paths_map.get(parsed.target, [])
        target_path = target_paths[0] if target_paths else None
        if not target_path:
            print(f"Error: Unknown target {parsed.target}")
            return 1

        success, msg = merge_config_into_file(target_path, parsed.target, mode=parsed.mode)
        print(msg)
        return 0 if success else 1

    if parsed.all:
        detected = detect_installed_clients()
        if not detected:
            print("No external client installations detected. Printing standard configuration snippets:")
            targets = ["cline", "cursor", "opencode", "claude", "zed"]
            output = {t: generate_snippet_for_client(t, mode=parsed.mode) for t in targets}
            print(json.dumps(output, indent=2))
            return 0

        print(f"Detected {len(detected)} client(s): {', '.join(detected.keys())}")
        all_ok = True
        for client, path in detected.items():
            success, msg = merge_config_into_file(path, client, mode=parsed.mode)
            print(f"[{'OK' if success else 'FAIL'}] {msg}")
            if not success:
                all_ok = False
        return 0 if all_ok else 1

    # Default action: show detected status and help
    detected = detect_installed_clients()
    print("SciVerifier Universal Agent Installer")
    print(f"Repo path: {get_repo_root()}")
    print("\nDetected clients on this system:")
    for c, p in detected.items():
        print(f"  - {c.capitalize()}: {p}")
    print("\nRun with --all to auto-configure all detected agents, or --print to view snippets.")
    return 0


if __name__ == "__main__":
    sys.exit(run_installer_cli(sys.argv[1:]))
