# HACS Release

## HACS Custom Repository Install Path

Voice Identity is installed through HACS as a custom repository (Integration type).

This documentation does not claim default HACS store listing.

## Validation Workflows

- `.github/workflows/hacs.yml` (HACS Validation)
- `.github/workflows/hassfest.yml` (Validate with hassfest)

Both workflows must pass before tagging and publishing a release.

## Release Checklist

Use docs/RELEASE_CHECKLIST.md for pre-release, release, and post-release gates.

## Tag and Release Expectations

- Review and, if needed, bump manifest version before release tagging.
- Create annotated tag.
- Create GitHub release with release notes.
- Verify HACS custom repository installation.

## Current Status

Repository is prepared for HACS and hassfest CI validation, with release gating defined by test and workflow outcomes.
