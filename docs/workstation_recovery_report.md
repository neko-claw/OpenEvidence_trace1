# Workstation recovery report

Date: 2026-08-12 (Asia/Shanghai)

## Source protection and Git recovery

- Original snapshot `D:\A_demo` was not deleted, reset, cleaned or overwritten.
- Its `.git` is a 56-byte file pointing to the missing old worktree metadata at
  `D:/lenovo/Desktop/A5_demo/.git/worktrees/A_demo`.
- `git status` and `git rev-parse` therefore failed in the copied snapshot.
- Remote probing failed with Windows TLS credential error
  `SEC_E_NO_CREDENTIALS`; `gh auth status` reported an invalid token.
- A filtered copy was created at `D:\A_demo_recovered`, excluding `.git`,
  `.pixi`, Python/test caches, temporary directories, local model/database/cache
  paths, `.env` and `log.md`.
- 358 included files were compared by SHA-256: no missing, extra or changed file.
- An independent repository and branch `feature/a1-a5-live-completion` were
  created. Commit `8d82924` is a filesystem recovery baseline, not the original
  `bb5218f` commit or its history.

## Key-file verification

`backend/`, `a1/ports/`, `a2/adapters/a3_evidence.py`,
`retrieval/a3_pool_adapter.py`, `a5/facade.py`, `contracts/a5/v0.4.0/` and
`ready.md` were all present after recovery.

## Machine and environment

- Windows; PowerShell
- Git 2.53.0.windows.3
- GitHub CLI 2.94.0 (authentication currently invalid)
- Pixi 0.76.1; locked Python 3.11.15 in the rebuilt environment
- Host Python observed: 3.11.4 (not used as the project dependency authority)
- GPU: NVIDIA GeForce RTX 5060 Laptop GPU, driver 592.01, 8151 MiB
- GitHub DNS resolved; A2 public-source network tests passed later in the task
- `NCBI_EMAIL`, runtime `NCBI_TOOL`, approved Guidelines, formal DEV/gold,
  medical reviews and model snapshots were not supplied

`/log.md` is ignored by the root `.gitignore` and is never staged.
