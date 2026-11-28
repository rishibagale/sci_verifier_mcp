"""Unit tests for the Universal Agent Installer, config merging, and framework adapters."""

import json
from pathlib import Path

from sci_verifier_mcp.frameworks import get_all_tools
from sci_verifier_mcp.installer import (
    AUTO_APPROVE_TOOLS,
    generate_snippet_for_client,
    merge_config_into_file,
)


def test_generate_snippet_cline():
    snippet = generate_snippet_for_client("cline", mode="local")
    assert "command" in snippet
    assert "args" in snippet
    assert "autoApprove" in snippet
    assert "check_equation_equivalence" in snippet["autoApprove"]
    assert snippet["disabled"] is False


def test_generate_snippet_uvx_mode():
    snippet = generate_snippet_for_client("cursor", mode="uvx")
    assert snippet["command"] == "uvx"
    assert any("git+https://" in arg for arg in snippet["args"])


def test_generate_snippet_zed():
    snippet = generate_snippet_for_client("zed", mode="local")
    assert "command" in snippet
    assert "path" in snippet["command"]
    assert "args" in snippet["command"]


def test_merge_config_preserves_existing_servers(tmp_path: Path):
    target_file = tmp_path / "cline_mcp_settings.json"
    initial_content = {
        "mcpServers": {
            "existing-server": {
                "command": "node",
                "args": ["server.js"]
            }
        }
    }
    target_file.write_text(json.dumps(initial_content), encoding="utf-8")

    success, msg = merge_config_into_file(target_file, "cline", mode="local")
    assert success is True

    # Verify backup created
    backup = target_file.with_suffix(".json.bak")
    assert backup.exists()

    # Verify merged content
    updated = json.loads(target_file.read_text(encoding="utf-8"))
    assert "mcpServers" in updated
    assert "existing-server" in updated["mcpServers"]
    assert "sci-verifier" in updated["mcpServers"]
    assert updated["mcpServers"]["sci-verifier"]["autoApprove"] == AUTO_APPROVE_TOOLS


def test_merge_config_zed_format(tmp_path: Path):
    target_file = tmp_path / "settings.json"
    initial_content = {"theme": "One Dark"}
    target_file.write_text(json.dumps(initial_content), encoding="utf-8")

    success, msg = merge_config_into_file(target_file, "zed", mode="local")
    assert success is True

    updated = json.loads(target_file.read_text(encoding="utf-8"))
    assert updated["theme"] == "One Dark"
    assert "context_servers" in updated
    assert "sci-verifier" in updated["context_servers"]


def test_frameworks_tool_export():
    tool_map = get_all_tools()
    assert len(tool_map) == 21
    assert "check_equation_equivalence" in tool_map
    assert "verify_ode_pde_solution" in tool_map
    assert "search_lean_premises" in tool_map
    assert "check_elastic_and_phonon_stability" in tool_map
    assert "export_audit_certificate" in tool_map

    # Test invoking tool via framework callable
    res = tool_map["check_equation_equivalence"](lhs="a + b", rhs="b + a", format="sympy")
    assert isinstance(res, dict)
    assert res["status"] == "verified"
