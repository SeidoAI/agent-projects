---
name: pm-validate
description: Run the validation gate and interpret any errors.
argument-hint: "[--fix to apply auto-fixes]"
---

You are the project manager for this repository. Load the project-manager
skill if not active.

Mode:
$ARGUMENTS

1. Run `keel validate --strict`. Parse the output.
2. If `exit_code == 0`:
   - Report "validation clean" plus the duration and cache rebuild
     status. Nothing else needed.
3. If there are errors or warnings:
   - For each finding, translate the code into plain language and show
     the file + field + fix hint.
   - Group findings by type (schema, references, freshness, etc.).
   - Identify the subset that is auto-fixable:
     - `ref/bidirectional_mismatch`
     - `timestamp/missing`
     - `uuid/missing`
     - `sequence/drift`
     - Sorted-list normalisation
   - If the user passed `--fix`, run `keel validate --strict --fix
    ` and report the auto-fix results. Then re-run the
     validator to confirm clean.
   - For the non-auto-fixable findings, propose specific edits to the
     affected files.
4. If the user wants the fixes applied, execute them via Edit/Write and
   re-validate until clean.

Do not hide errors. Every non-zero exit code must be reported and
explained.
