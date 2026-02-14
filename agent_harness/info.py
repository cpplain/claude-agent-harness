"""
Info Command Handlers
=====================

Handlers for the `agent-harness info` subcommand.
Provides templates, schema, presets, and documentation.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_harness.presets import get_preset, list_presets
from agent_harness.schema import generate_schema


def _format_template_human(template: dict) -> str:
    """Format template information for human reading."""
    lines = [
        f"Template: {template['name']}",
        f"Description: {template['description']}",
        f"Target Path: {template['target_path']}",
        "",
        "Content:",
        "-" * 60,
        template["content"],
        "-" * 60,
    ]
    return "\n".join(lines)


def _format_preset_human(preset: dict) -> str:
    """Format preset information for human reading."""
    lines = [
        f"Preset: {preset['name']}",
        f"Description: {preset['description']}",
        "",
        "Configuration:",
    ]

    for key, value in preset["config"].items():
        if isinstance(value, list):
            lines.append(f"  {key}:")
            for item in value:
                lines.append(f"    - {item}")
        elif isinstance(value, dict):
            lines.append(f"  {key}:")
            for k, v in value.items():
                lines.append(f"    {k} = {v}")
        else:
            lines.append(f"  {key} = {value}")

    return "\n".join(lines)


def _format_schema_human(schema: dict) -> str:
    """Format schema information for human reading."""
    lines = ["Configuration Schema", "=" * 60, ""]

    def format_field(name: str, field_info: dict, indent: int = 0) -> None:
        prefix = "  " * indent
        lines.append(f"{prefix}{name}:")

        if "description" in field_info:
            lines.append(f"{prefix}  Description: {field_info['description']}")

        if "type" in field_info:
            lines.append(f"{prefix}  Type: {field_info['type']}")

        if "enum" in field_info:
            lines.append(f"{prefix}  Options: {', '.join(field_info['enum'])}")

        if "options" in field_info:
            lines.append(f"{prefix}  Options: {', '.join(str(o) for o in field_info['options'])}")

        if "default" in field_info:
            default = field_info["default"]
            if isinstance(default, str):
                lines.append(f'{prefix}  Default: "{default}"')
            else:
                lines.append(f"{prefix}  Default: {default}")

        # Recurse into nested fields
        if "fields" in field_info:
            lines.append(f"{prefix}  Fields:")
            for sub_name, sub_info in field_info["fields"].items():
                format_field(sub_name, sub_info, indent + 2)

        lines.append("")

    for name, info in schema.items():
        format_field(name, info)

    return "\n".join(lines)


def get_templates_dir() -> Path:
    """Get the path to the templates directory."""
    return Path(__file__).parent / "templates"


def get_template(name: str) -> dict | None:
    """Get template by name.

    Args:
        name: Template filename (e.g. "config.toml")

    Returns:
        Template dict with name, description, target_path, and content
    """
    templates_dir = get_templates_dir()
    template_path = templates_dir / name

    if not template_path.exists():
        return None

    # Determine description and target path based on template name
    templates_meta = {
        "config.toml": {
            "description": "Main harness configuration",
            "target_path": ".agent-harness/config.toml",
        },
        "spec.md": {
            "description": "Project specification template",
            "target_path": ".agent-harness/spec.md",
        },
        "init.md": {
            "description": "Initialization phase prompt",
            "target_path": ".agent-harness/prompts/init.md",
        },
        "build.md": {
            "description": "Building phase prompt",
            "target_path": ".agent-harness/prompts/build.md",
        },
    }

    meta = templates_meta.get(name, {
        "description": "Template file",
        "target_path": f".agent-harness/{name}",
    })

    return {
        "name": name,
        "description": meta["description"],
        "target_path": meta["target_path"],
        "content": template_path.read_text(),
    }


def list_templates() -> list[dict]:
    """List all available templates by discovering from filesystem.

    Returns:
        List of template dicts with name and description
    """
    templates = []
    templates_dir = get_templates_dir()

    # Discover all files in templates directory
    if templates_dir.exists():
        for template_file in sorted(templates_dir.iterdir()):
            if template_file.is_file():
                template = get_template(template_file.name)
                if template:
                    templates.append({
                        "name": template["name"],
                        "description": template["description"],
                        "target_path": template["target_path"],
                    })

    return templates


def get_guide() -> dict:
    """Get the setup guide.

    Returns:
        Guide dict with title and sections
    """
    docs_dir = Path(__file__).parent.parent / "docs"
    guide_path = docs_dir / "setup-guide.md"

    if not guide_path.exists():
        return {
            "title": "Harness Setup Guide",
            "sections": [],
            "content": "Setup guide not found.",
        }

    content = guide_path.read_text()

    # Parse markdown sections by ## headers
    sections = []
    current_section = None
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## "):
            # Save previous section
            if current_section:
                sections.append({
                    "title": current_section,
                    "content": "\n".join(current_lines).strip(),
                })
            # Start new section
            current_section = line[3:].strip()
            current_lines = []
        elif current_section:
            current_lines.append(line)

    # Save last section
    if current_section:
        sections.append({
            "title": current_section,
            "content": "\n".join(current_lines).strip(),
        })

    return {
        "title": "Harness Setup Guide",
        "sections": sections,
        "content": content,
    }


def cmd_info_template(name: str | None, list_templates_flag: bool, all_templates_flag: bool, json_output: bool) -> None:
    """Handle `agent-harness info template` command.

    Args:
        name: Template name to display
        list_templates_flag: Whether to list all templates
        all_templates_flag: Whether to get all templates with content
        json_output: Whether to output JSON
    """
    if all_templates_flag:
        # Get all templates with full content
        templates = []
        for t in list_templates():
            template = get_template(t["name"])
            if template:
                templates.append(template)

        if json_output:
            print(json.dumps(templates, indent=2))
        else:
            for i, template in enumerate(templates):
                if i > 0:
                    print("\n" + "=" * 60 + "\n")
                print(_format_template_human(template))
        return

    if list_templates_flag:
        templates = list_templates()
        if json_output:
            print(json.dumps(templates, indent=2))
        else:
            print("Available Templates:")
            print("-" * 60)
            for t in templates:
                print(f"  {t['name']:<20} - {t['description']}")
                print(f"  {'':20}   Target: {t['target_path']}")
                print()
        return

    if not name:
        print("Error: --name, --list, or --all required")
        print("Usage: agent-harness info template [--name NAME] [--list] [--all]")
        return

    template = get_template(name)
    if not template:
        print(f"Error: Template not found: {name}")
        print("\nAvailable templates:")
        for t in list_templates():
            print(f"  - {t['name']}")
        return

    if json_output:
        print(json.dumps(template, indent=2))
    else:
        print(_format_template_human(template))


def cmd_info_schema(json_output: bool) -> None:
    """Handle `agent-harness info schema` command.

    Args:
        json_output: Whether to output JSON
    """
    schema = generate_schema()

    if json_output:
        print(json.dumps(schema, indent=2))
    else:
        print(_format_schema_human(schema))


def cmd_info_preset(name: str | None, list_presets_flag: bool, json_output: bool) -> None:
    """Handle `agent-harness info preset` command.

    Args:
        name: Preset name to display
        list_presets_flag: Whether to list all presets
        json_output: Whether to output JSON
    """
    if list_presets_flag:
        presets = list_presets()
        if json_output:
            print(json.dumps(presets, indent=2))
        else:
            print("Available Presets:")
            print("-" * 60)
            for p in presets:
                print(f"  {p['name']:<20} - {p['description']}")
            print()
        return

    if not name:
        print("Error: --name or --list required")
        print("Usage: agent-harness info preset [--name NAME] [--list]")
        return

    preset = get_preset(name)
    if not preset:
        print(f"Error: Preset not found: {name}")
        print("\nAvailable presets:")
        for p in list_presets():
            print(f"  - {p['name']}")
        return

    if json_output:
        print(json.dumps(preset, indent=2))
    else:
        print(_format_preset_human(preset))


def cmd_info_guide(json_output: bool) -> None:
    """Handle `agent-harness info guide` command.

    Args:
        json_output: Whether to output JSON
    """
    guide = get_guide()

    if json_output:
        print(json.dumps(guide, indent=2))
    else:
        # Just print the full content for human reading
        print(guide["content"])
