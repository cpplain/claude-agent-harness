# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [0.1.0] - 2026-02-14

Initial release of Agent Harness.

### Added

- **CLI commands** — `run`, `verify`, `init`, and `info` for executing agents, checking setup, scaffolding config, and accessing templates/schemas
- **Phase-based workflows** — Sequential phase execution with `run_once` and path-based conditions; session state persists across runs
- **Progress tracking** — JSON checklist, notes file, or none; automatic completion detection for checklists
- **SDK-native sandbox** — Process isolation, network domain allowlists, and declarative permission rules (allow/deny patterns)
- **Error recovery** — Circuit breaker with exponential backoff for transient failures
- **MCP server integration** — Configure Model Context Protocol servers with environment variable expansion
- **Built-in presets** — Python, Go, Rust, Node.js, and read-only configurations
- **Setup verification** — 10 pre-flight checks covering Python version, SDK, auth, config validity, and more
- **Claude Code plugin** — `/agent-harness` skill for guided setup
- **Example projects** — `claude-ai-clone` (Next.js with Puppeteer MCP) and `simple-calculator` (minimal Python)

[unreleased]: https://github.com/cpplain/claude-agent-harness/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cpplain/claude-agent-harness/releases/tag/v0.1.0
