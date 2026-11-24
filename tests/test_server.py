"""Integration tests for FastMCP server initialization, tool registration, and prompts."""

from sci_verifier_mcp.server import mcp


def test_fastmcp_server_initialization():
    assert mcp.name == "sci_verifier_mcp"


def test_all_twelve_tools_registered():
    # Verify that all 12 required tools are registered in FastMCP
    registered_tools = mcp._tool_manager.list_tools()
    tool_names = {t.name for t in registered_tools}

    expected_tools = {
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

    assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"
    assert len(tool_names) == 12


def test_prompt_registered():
    registered_prompts = mcp._prompt_manager.list_prompts()
    prompt_names = {p.name for p in registered_prompts}
    assert "audit_derivation" in prompt_names


def test_tool_execution_via_server():
    # Test direct execution of tool logic through registered wrapper
    tool_fn = mcp._tool_manager.get_tool("check_equation_equivalence")
    assert tool_fn is not None
    res = tool_fn.fn(lhs="x**2 - 1", rhs="(x - 1)*(x + 1)", format="sympy")
    assert res["status"] == "verified"
