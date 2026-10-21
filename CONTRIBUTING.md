# Contributing

Thank you for helping. The library is small on purpose: one tab system that
many apps share, so every change must stay general and keep working for all of
them.

## Before you start

- Read `README.md` for what the library does and `AGENTS.md` for how it is
  laid out. The rules there apply to people too.
- For a bigger change, open an issue first and describe the problem it solves.

## Making a change

1. Keep it general. Anything one app needs becomes an option whose default
   changes nothing for others.
2. Add or update a test:
   - tabs page behaviour in `test/run.py`, tree behaviour in `test/tree_run.py`
   - window behaviour in `src/runtime_tests.rs`
   - pure logic next to the code
3. Update the docs to match: `README.md`, `web/tabs.d.ts` or `web/tree.d.ts`, and `examples/basic`.
4. Add a line under **Unreleased** at the top of `CHANGELOG.md`. If apps must
   change something, write the exact steps under **Upgrade**. The maintainer
   sets the version when releasing.
5. Run the checks. All of them must pass, with no warnings:
   ```
   cargo fmt --check && cargo clippy --all-targets && cargo test
   python test/run.py            # needs Python 3.11+, playwright and Google Chrome
   python test/tree_run.py
   python test/terminal_run.py
   (cd examples/basic/src-tauri && cargo build)
   python scripts/doctor.py examples/basic
   ```
6. If you touched dragging between windows, try it by hand on macOS. No
   test can drive the real mouse.

## Style

- Write plain English in docs, comments and messages, with short sentences.
- Comments say why, not what.
- In Rust, read the tab model only through `Inner::model()`, never hold its
  lock while calling Tauri or the app, and return errors instead of panicking.

## Licence

By contributing you agree that your work is released under the MIT licence.
