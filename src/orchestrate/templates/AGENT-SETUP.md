# Agent and harness setup: {{name}}

This project's harness configuration. Roles and models are in `orchestrate.toml`; this file holds what the harnesses need around them.

## Adapters

- Harness adapters in `adapters/harness-<name>`, land adapter in `adapters/land-<name>`. Each passes `orch conform`.

## Permissions

- `setup-permissions.py` here is for the owner to read and run: agents never widen their own permissions.
- What it allows, and what is left to the harness's classifier on purpose, is listed in the script.

## Machine

- Shared services, ports and locks: (fill in at setup).
