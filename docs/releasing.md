# Build and publish a GitHub release

[Back to README](../README.md)

## Before a release

1. Confirm the release's version matches in `pyproject.toml` and `eclipse/__init__.py`.
2. Update README behavior, command examples and current screenshots.
3. Review changed files for personal data. Choose and add the project's license
   before presenting it as open source; this repository currently has no license file.
4. Run tests and ensure the GitHub workflow succeeds for the exact commit to release.

## Build locally

From the repository root:

```bash
.venv/bin/python -m pip install build twine
.venv/bin/python -m build --outdir dist/release
.venv/bin/python -m twine check dist/release/*
```

Use a fresh output directory for each release. The output for 0.3.0 is
`eclipse_mac-0.3.0-py3-none-any.whl` and `eclipse_mac-0.3.0.tar.gz`.
The source archive includes installation instructions, installer, documentation,
tests and packaged resources. The wheel includes the runtime package and its
scripts/manifests/config; install it with pip, not by unzipping it manually.

Test the wheel in an isolated environment outside the checkout (replace the two
absolute example paths with your repository and wheel paths):

```bash
python3 -m venv /tmp/eclipse-release-check
/tmp/eclipse-release-check/bin/python -m pip install /absolute/path/to/eclipse_mac-0.3.0-py3-none-any.whl
cd /tmp
/tmp/eclipse-release-check/bin/python /absolute/path/to/Eclipse/tools/check_distribution.py
```

Repeat in a different empty environment with the source archive. The smoke check
verifies imports, version consistency, package resources and CLI entry points; it
does not perform a real security scan or change system settings.

GitHub Actions performs those package checks too, and exposes the built files as
an **eclipse-distributions** workflow artifact. Workflow artifacts are not Releases.

## Publish

Create a GitHub Release for the tested commit and attach both distribution files.
Follow [GitHub's release instructions](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
Include the version, requirements, installation commands, notable changes and
known limitations. Attach checksums if desired. GitHub's automatic source ZIP is
separate from the Python source distribution built above.

The workflow intentionally does not create tags, push commits, publish to PyPI,
or publish a Release. Those are maintainer actions. No repository URL or release
availability is assumed by the installation instructions.
