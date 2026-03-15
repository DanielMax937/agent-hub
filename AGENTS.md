# AGENT Instructions for agent-hub

## Workflow Expectations

- When using the superpowers development workflow (`start-workflow` and related skills), you MUST follow the prescribed sequence strictly:
  - Use `brainstorming` before any creative or implementation work.
  - Use `using-git-worktrees` to create an isolated git worktree for feature or test work, even for small changes, unless the user explicitly waives this requirement.
  - Use `writing-plans` to create an implementation plan in `docs/plans/` before touching code.
  - Use either `subagent-driven-development` or `executing-plans` to implement the plan.
  - Use `test-driven-development` during implementation.
  - Use `requesting-code-review` and/or spec/quality reviewers between tasks as appropriate.
  - Use `verification-before-completion` before claiming success.
  - Use `finishing-a-development-branch` at the end of the workflow to decide how to integrate the work (merge, PR, keep, or discard) and to clean up any worktrees.

## Testing Conventions

- Python tests should live under `tests/` and use `pytest`.
- Test modules should import the project code via standard Python imports (e.g., `from agent_hub import ...`).

