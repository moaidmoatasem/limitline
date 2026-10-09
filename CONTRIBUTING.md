# Contributing to Limitline

Thank you for your interest in contributing! 

Limitline is built as a highly portable, predominantly single-file application. 

## Guidelines

- Limitline's core stays standard library only.
- Any optional dependencies (like `pystray` or `Pillow`) must be strictly opt-in and fail gracefully when missing.
- Keep Python 3.8+ compatibility.
- Ensure that you do not send, log, or store the user's message text or tokens. Privacy is paramount.

## Getting Started

If you are using an AI coding assistant (like Claude Code, Cursor, GitHub Copilot), please point it to the [`AGENTS.md`](AGENTS.md) file, which contains a detailed overview of the layout, rules, and local runtime files.

## Testing

Limitline has a custom test runner that doesn't require `pytest`.
Run tests via:
```bash
python tests/test_core.py
```

To run a self-test of the UI (opens and closes windows):
```bash
python limitline.py --selftest
```

## Pull Requests

1. Make every PR small, independently reviewable, and reversible.
2. Run the tests before submitting.
3. If adding a UI feature, please include screenshots.
