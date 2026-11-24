"""End-to-end test verifying the FastMCP server boots over stdio and responds to JSON-RPC tools/list."""

import json
import subprocess
import sys
from pathlib import Path


def test_server_stdio_handshake():
    root_dir = Path(__file__).resolve().parent.parent
    python_exe = root_dir / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    # Launch server as subprocess over stdio
    proc = subprocess.Popen(
        [str(python_exe), "-m", "sci_verifier_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(root_dir),
        text=True,
    )

    try:
        # 1. Send JSON-RPC initialize request
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-verifier-client", "version": "1.0.0"}
            }
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()

        init_resp_line = proc.stdout.readline()
        assert init_resp_line, f"Server closed stdout without response. Stderr: {proc.stderr.read()}"
        init_resp = json.loads(init_resp_line)
        assert init_resp.get("id") == 1
        assert "result" in init_resp

        # 2. Send initialized notification
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()

        # 3. Send tools/list request
        tools_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        proc.stdin.write(json.dumps(tools_req) + "\n")
        proc.stdin.flush()

        tools_resp_line = proc.stdout.readline()
        assert tools_resp_line, "Server did not respond to tools/list"
        tools_resp = json.loads(tools_resp_line)
        assert tools_resp.get("id") == 2
        tools_list = tools_resp.get("result", {}).get("tools", [])
        tool_names = {t["name"] for t in tools_list}

        expected = {
            "check_equation_equivalence",
            "check_dimensional_analysis",
            "check_smt_claim",
            "verify_lean4_proof",
            "simplify_tensor_expr",
            "validate_crystal_structure",
            "check_stoichiometry_and_valence",
            "verify_material_properties",
            "check_novel_structure_prior_art",
            "verify_citation",
            "audit_bibliography",
            "find_similar_papers",
        }
        assert expected.issubset(tool_names), f"Missing tools over stdio: {expected - tool_names}"
        assert len(tools_list) == 12

    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    test_server_stdio_handshake()
    print("ALL STDIO HANDSHAKE CHECKS PASSED!")
