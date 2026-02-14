"""
Preset Configurations
=====================

Embedded preset configurations for common use cases.
Each preset provides recommended settings for specific project types.
"""

from __future__ import annotations

PRESETS = {
    "python": {
        "name": "python",
        "description": "Python development with pip/uv and PyPI access",
        "config": {
            "security.sandbox.network.allowed_domains": [
                "pypi.org",
                "files.pythonhosted.org",
                "github.com",
            ],
            "security.permissions.allow": [
                "Bash(python *)",
                "Bash(pip *)",
                "Bash(uv *)",
                "Bash(git *)",
            ],
        },
    },
    "go": {
        "name": "go",
        "description": "Go development with module proxy access",
        "config": {
            "security.sandbox.network.allowed_domains": [
                "proxy.golang.org",
                "sum.golang.org",
                "storage.googleapis.com",
                "github.com",
            ],
            "security.permissions.allow": [
                "Bash(go *)",
                "Bash(git *)",
            ],
        },
    },
    "rust": {
        "name": "rust",
        "description": "Rust development with crates.io access",
        "config": {
            "security.sandbox.network.allowed_domains": [
                "crates.io",
                "static.crates.io",
                "github.com",
            ],
            "security.permissions.allow": [
                "Bash(cargo *)",
                "Bash(rustc *)",
                "Bash(git *)",
            ],
        },
    },
    "web-nodejs": {
        "name": "web-nodejs",
        "description": "Node.js/npm with registry access and local dev server binding",
        "config": {
            "security.sandbox.network.allowed_domains": [
                "registry.npmjs.org",
                "github.com",
                "cdn.jsdelivr.net",
            ],
            "security.sandbox.network.allow_local_binding": True,
            "security.permissions.allow": [
                "Bash(npm *)",
                "Bash(node *)",
                "Bash(npx *)",
                "Bash(git *)",
            ],
        },
    },
    "read-only": {
        "name": "read-only",
        "description": "Code analysis only - no write tools or network access",
        "config": {
            "tools.builtin": ["Read", "Glob", "Grep"],
            "security.permission_mode": "bypassPermissions",
            "security.sandbox.network.allowed_domains": [],
        },
    },
}


def get_preset(name: str) -> dict | None:
    """Get a preset configuration by name.

    Args:
        name: Preset name (e.g. "python", "web-nodejs")

    Returns:
        Preset dict with name, description, and config, or None if not found
    """
    return PRESETS.get(name)


def list_presets() -> list[dict]:
    """List all available presets.

    Returns:
        List of preset dicts with name and description
    """
    return [
        {"name": p["name"], "description": p["description"]}
        for p in PRESETS.values()
    ]
