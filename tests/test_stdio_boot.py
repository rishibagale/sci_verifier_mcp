"""End-to-end test verifying the FastMCP server boots over stdio and responds to JSON-RPC tools/list."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_server_stdio_handshake():
    root_dir = Path(__file__).resolve().parent.parent
    python_exe = root_dir / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_dir / "src")

    # Launch server as subprocess over stdio
    proc = subprocess.Popen(
        [str(python_exe), "-m", "sci_verifier_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(root_dir),
        env=env,
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
            "verify_ode_pde_solution",
            "check_limiting_cases",
            "verify_simulation_invariants",
            "verify_lean4_proof",
            "search_lean_premises",
            "simplify_tensor_expr",
            "validate_crystal_structure",
            "check_stoichiometry_and_valence",
            "verify_material_properties",
            "check_novel_structure_prior_art",
            "check_elastic_and_phonon_stability",
            "relax_and_score_mlip",
            "verify_citation",
            "audit_bibliography",
            "find_similar_papers",
            "verify_claim_against_paper",
            "track_recent_discoveries",
            "export_audit_certificate",
        }
        assert expected.issubset(tool_names), f"Missing tools over stdio: {expected - tool_names}"
        assert len(tools_list) == 21

        # 4. Send prompts/list request
        prompts_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/list",
            "params": {}
        }
        proc.stdin.write(json.dumps(prompts_req) + "\n")
        proc.stdin.flush()

        prompts_resp_line = proc.stdout.readline()
        assert prompts_resp_line, "Server did not respond to prompts/list"
        prompts_resp = json.loads(prompts_resp_line)
        assert prompts_resp.get("id") == 3
        prompt_names = {p["name"] for p in prompts_resp.get("result", {}).get("prompts", [])}
        assert "audit_derivation" in prompt_names

        # 5. Send prompts/get request
        prompt_get_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "prompts/get",
            "params": {
                "name": "audit_derivation",
                "arguments": {"derivation_text": "E = m c^2", "domain": "physics"}
            }
        }
        proc.stdin.write(json.dumps(prompt_get_req) + "\n")
        proc.stdin.flush()

        prompt_get_line = proc.stdout.readline()
        assert prompt_get_line, "Server did not respond to prompts/get"
        prompt_get_resp = json.loads(prompt_get_line)
        assert prompt_get_resp.get("id") == 4
        messages = prompt_get_resp.get("result", {}).get("messages", [])
        assert len(messages) >= 1

        # 6. Send tools/call requests across domains and verify unified contract
        tool_calls = [
            (5, "check_equation_equivalence", {"lhs": "(x+1)**2", "rhs": "x**2 + 2*x + 1", "format": "sympy"}, "verified"),
            (6, "check_dimensional_analysis", {"equation": "E = m * c**2", "symbol_units": {"E": "joule", "m": "kg", "c": "m/s"}}, "verified"),
            (7, "check_stoichiometry_and_valence", {"formula_or_reaction": "2 H2 + O2 -> 2 H2O"}, "verified"),
            (8, "verify_ode_pde_solution", {"equation": "y''(x) + y(x) = 0", "candidate_solution": "cos(x)", "boundary_conditions": {"y(0)": 1}}, "verified"),
            (9, "check_limiting_cases", {"expr": "sin(x)/x", "limits": {"x": "0"}, "expected": {"x": "1"}}, "verified"),
            (10, "verify_simulation_invariants", {"data": [10.0, 10.0, 10.0], "checks": ["conservation"]}, "verified"),
        ]
        for req_id, tool_name, arguments, expected_status in tool_calls:
            call_req = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments}
            }
            proc.stdin.write(json.dumps(call_req) + "\n")
            proc.stdin.flush()

            call_resp_line = proc.stdout.readline()
            assert call_resp_line, f"Server did not respond to tools/call for {tool_name}"
            call_resp = json.loads(call_resp_line)
            assert call_resp.get("id") == req_id
            result = call_resp.get("result", {})
            assert not result.get("isError", False), f"Tool {tool_name} returned error: {result}"
            content_items = result.get("content", [])
            assert content_items, f"Empty content for {tool_name}"
            payload = json.loads(content_items[0]["text"])
            assert payload["status"] == expected_status
            assert {"status", "summary", "details", "sources"}.issubset(payload.keys())

    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    test_server_stdio_handshake()
    print("ALL STDIO HANDSHAKE CHECKS PASSED!")
