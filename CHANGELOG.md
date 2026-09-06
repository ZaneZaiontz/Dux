# Changelog

All notable changes to Dux will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Dux now holds a private hypothesis about your problem and guides you toward it
- Agent graph split into hypothesize, assess, probe and affirm nodes
- Conversations persist in Postgres, so history survives a restart
- Postgres service added to the backend Docker deployment
- Tests for the agent graph that run against a stub model instead of Gemini
- Dux can read the project you point it at, so it reasons about your real code
- Code reading tools for listing, searching and reading files
- Secrets, dependencies and ignored files are never readable, and the project is
  mounted read-only

### Fixed
- N/A

### Changed
- The generate endpoint now takes a conversation id so turns thread together
- Dux investigates the code before forming an opinion, and keeps that research out
  of your conversation

## [0.0.1] - 2026-01-06

### Added
- Added base folder layout
- Added base Docker deployment for backend app
- Created simple FastAPI server to send requests to
- Created simple langgraph agent using gemini (2.5-flash)
- Created simple scripts in /tools to test the server LLM generation

### Fixed
- N/A

### Changed
- N/A
