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
- Dux answers a plain question about your code instead of making you guess it
- Follow-up questions look at your code again rather than reusing what Dux found
  earlier in the conversation
- The chat tool no longer gives up on a reply that takes a while to arrive
- Starting Dux no longer waits on the model before answering anything
- Dux no longer congratulates you for an answer you never gave. It now
  judges only what you actually said, and asks a question when unsure

### Changed
- The generate endpoint now takes a conversation id so turns thread together
- Dux now talks to any OpenAI compatible endpoint, so it runs on a local model by
  default and on a cloud model if you prefer
- Dux says so at startup when your model cannot use tools, rather than quietly
  reading none of your code
- Dux asks your model server what it has loaded, so the model name is optional
  and the size of a file it will read is scaled to the context window
- Replies stream back as they are written, with progress while Dux investigates
- Every run is traced. Phoenix shows the prompts and replies behind each step, and
  Grafana shows the timings, both fed from one collector
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
