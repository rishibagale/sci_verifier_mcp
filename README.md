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

## Universal Client & Agent Configurations

You can configure SciVerifier for any AI coding assistant automatically or by copying the client configuration snippets below.

### Automatic One-Command Setup
Automatically detect all installed coding agents on your machine and merge SciVerifier into their active configurations:

```bash
# Auto-detect and configure all installed agents (Cline, OpenCode, Cursor, Windsurf, Zed, Claude)
sci-verifier-config --all

# Or print configuration for a specific target without modifying files
sci-verifier-config --target cline --print
```

---

### Zero-Install Remote Execution (via `uvx`)
Any agent can run SciVerifier globally without cloning or installing dependencies locally:

```json
{
  "command": "uvx",
  "args": ["--from", "git+https://github.com/rishibagale/sci_verifier_mcp.git", "sci-verifier-mcp"]
}
```

---

### Client-Specific Configurations

#### 1. Cline & Roo Code (VS Code Extension)
In `cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "uv",
      "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
      "env": {
        "MP_API_KEY": ""
      },
      "disabled": false,
      "autoApprove": [
        "check_equation_equivalence",
        "check_dimensional_analysis",
        "validate_crystal_structure",
        "check_stoichiometry_and_valence",
        "verify_citation"
      ]
    }
  }
}
```

#### 2. OpenCode (CLI & Editor Agent)
In `opencode.json` (project root) or `~/.config/opencode/mcp.json`:

```json
{
  "mcp": {
    "servers": {
      "sci-verifier": {
        "command": "uv",
        "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
        "env": {
          "MP_API_KEY": ""
        }
      }
    }
  }
}
```

#### 3. Cursor IDE
This repository includes a project-level [`.cursor/mcp.json`](file:///.cursor/mcp.json) that Cursor detects automatically when the folder is opened. For global configuration in `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "uv",
      "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
      "env": {
        "MP_API_KEY": ""
      }
    }
  }
}
```

#### 4. Windsurf (Codeium)
In `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "uv",
      "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
      "env": {
        "MP_API_KEY": ""
      }
    }
  }
}
```

#### 5. Zed Editor
In `settings.json` (or `.zed/settings.json`):

```json
{
  "context_servers": {
    "sci-verifier": {
      "command": {
        "path": "uv",
        "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
        "env": {
          "MP_API_KEY": ""
        }
      }
    }
  }
}
```

#### 6. Claude Desktop
In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "sci-verifier": {
      "command": "uv",
      "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"],
      "env": {
        "MP_API_KEY": ""
      }
    }
  }
}
```

#### 7. Continue.dev
In `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "sci-verifier",
      "command": "uv",
      "args": ["--directory", "/path/to/sci-verifier-mcp", "run", "sci-verifier-mcp"]
    }
  ]
}
```

---

## Python Multi-Agent Frameworks (LangGraph, CrewAI, AutoGen)

SciVerifier can be used directly as a Python library in multi-agent pipelines:

```python
from sci_verifier_mcp.frameworks import get_all_tools, get_langchain_tools

# 1. Raw Python callable dictionary
tools = get_all_tools()
result = tools["check_equation_equivalence"](lhs="E", rhs="m * c**2")

# 2. LangChain / LangGraph / CrewAI tools
langchain_tools = get_langchain_tools()
```

---

## Testing & Transport Options

### Transports (`stdio` & Streamable HTTP)
```bash
# Default stdio transport (for Claude Desktop, Cline, Cursor, OpenCode)
uv run sci-verifier-mcp

# Streamable HTTP transport
uv run sci-verifier-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

### Automated Tests & Quality Checks
```bash
# Default offline test suite
uv run pytest -m "not live" -v

# Opt-in live API integration checks (Crossref, OpenAlex, arXiv, Loogle, OPTIMADE)
uv run pytest -m live -v

# Lint and type-check
uv run ruff check src tests
uv run mypy src
```

---

## License

MIT License.
