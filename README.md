# SciVerifier MCP Server

A modular Model Context Protocol (MCP) server for mathematicians, theoretical physicists, and materials scientists. SciVerifier equips AI agents with empirical, symbolic, and formal verification tools to audit AI-generated scientific derivations, equations, formal proofs, crystal structures, material property claims, citations, and prior art.

---

## Features

- **Mathematical & Symbolic Verification**:
  - `check_equation_equivalence`: Two-pronged verification via SymPy symbolic simplification and randomized numerical domain sampling with counterexample extraction.
  - `check_dimensional_analysis`: Multi-term dimensional consistency using Pint across SI, natural units ($\hbar = c = 1$), and materials units ($\text{eV}$, $\text{GPa}$, $\text{\AA}$, $\text{S/cm}$).
  - `check_smt_claim`: Proves or refutes inequalities, domain constraints, and logical implications via AST-safe Z3-Solver integration.
- **Formal Proofs & Tensors**:
  - `verify_lean4_proof`: Sandboxed Lean 4 compiler diagnostics with strict rejection of placeholder cheats (`sorry`, `admit`) and unverified `axiom` assertions.
  - `simplify_tensor_expr`: Cadabra2 plugin stub for QFT and General Relativity tensor algebra with graceful degradation.
- **Materials Science Verification**:
  - `validate_crystal_structure`: CIF and POSCAR parsing, minimum interatomic distance thresholding ($< 0.7\text{ \AA}$ indicates unphysical overlap), and space group symmetry analysis via `spglib`.
  - `check_stoichiometry_and_valence`: Validates chemical formulas for plausible oxidation state electroneutrality and checks mass/charge conservation for chemical reactions.
  - `verify_material_properties`: Queries Materials Project API (`MP_API_KEY`) to cross-check band gap, formation energy, stability, and energy above hull.
  - `check_novel_structure_prior_art`: Federated OPTIMADE search across Materials Project, Crystallography Open Database (COD), and AFLOW to test novelty claims.
- **Literature & Citation Auditing**:
  - `verify_citation`: Cross-validates DOIs and arXiv IDs against Crossref and arXiv to eliminate hallucinated papers.
  - `audit_bibliography`: Concurrently audits BibTeX strings or citation lists with bounded rate limiting.
  - `find_similar_papers`: Multi-database similarity search across Semantic Scholar, OpenAlex, arXiv (including `cond-mat.mtrl-sci`), and INSPIRE-HEP.
- **Orchestration Prompt & Skill**:
  - Built-in MCP prompt `audit_derivation` guiding connected clients through a 5-stage verification loop.
  - Companion `SKILL.md` encoding researcher verification principles.

---

## Installation & Setup

### Requirements
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or `pip`

### Install with uv
```bash
# Clone the repository
git clone <repo-url>
cd sci-verifier-mcp

# Create virtual environment and install in editable mode
uv venv .venv
uv pip install -e ".[dev]"
```

---

## Environment Variables

All API keys are optional. When unset, corresponding online tools gracefully degrade to `status: "unavailable"` with setup instructions while local tools continue functioning.

| Variable | Description |
|---|---|
| `MP_API_KEY` | Materials Project API key for computed property verification ([Get Key](https://next-gen.materialsproject.org/api)) |
| `CROSSREF_MAILTO` | Contact email for Crossref polite pool access (defaults to `sci-verifier@example.com`) |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional API key for higher Semantic Scholar rate limits |
| `OPENALEX_API_KEY` | Optional API key for OpenAlex API |
| `CACHE_DB_PATH` | Path to persistent SQLite cache database (defaults to `~/.cache/sci_verifier_mcp/cache.db`) |

---

## Client Configurations

### 1. Claude Desktop
Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/sci-verifier-mcp",
        "run",
        "sci-verifier-mcp"
      ],
      "env": {
        "MP_API_KEY": "your_materials_project_key",
        "CROSSREF_MAILTO": "your_email@example.com"
      }
    }
  }
}
```

### 2. Cursor
In Cursor Settings $\to$ Features $\to$ MCP Servers $\to$ **Add New MCP Server**:
- **Name**: `sci-verifier`
- **Type**: `command`
- **Command**: `uv --directory /path/to/sci-verifier-mcp run sci-verifier-mcp`

### 3. Gemini CLI / Antigravity
Add to your `gemini.json` / Antigravity MCP server settings:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "python",
      "args": ["-m", "sci_verifier_mcp.server"],
      "cwd": "/path/to/sci-verifier-mcp",
      "env": {
        "MP_API_KEY": "your_materials_project_key"
      }
    }
  }
}
```

---

## Testing

Run the test suite using `pytest`:

```bash
uv run pytest -v
```

---

## License

MIT License.
