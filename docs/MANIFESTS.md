# Package Manifests

`xian-contracts` packages use package-local `contract-bundle.json` files as the
handoff contract for the contracting hub and other catalog tooling.

The manifest schema is the same `xian.contract_bundle.v1` shape used by product
repos such as `xian-dex`, but each standalone package stores its manifest inside
the package directory:

```text
contracts/<package-name>/
  README.md
  contract-bundle.json
  src/
    con_*.py
  tests/
```

## Required Shape

```json
{
  "schema": "xian.contract_bundle.v1",
  "schema_version": 1,
  "name": "nameservice",
  "display_name": "Nameservice",
  "version": "0.1.0",
  "description": "Renewable on-chain name registry.",
  "source": {
    "repo": "https://github.com/xian-technology/xian-contracts"
  },
  "contracts": [
    {
      "name": "con_nameservice",
      "role": "registry",
      "path": "src/con_nameservice.py",
      "sha256": "<sha256-of-source>",
      "deploy_order": 10
    }
  ]
}
```

Required package fields:

- `schema`: always `xian.contract_bundle.v1`
- `schema_version`: always `1`
- `name`: package folder slug
- `display_name`: reader-facing package name
- `version`: package release version
- `description`: concise package purpose
- `source.repo`: canonical owner repository
- `contracts`: non-empty list of source artifacts in this package

Required contract fields:

- `name`: deployed Xian contract name, always starting with `con_`
- `role`: stable semantic role inside the package, such as `registry`,
  `token`, `checker`, or `adapter`
- `path`: package-relative source path under `src/`
- `sha256`: SHA-256 of the UTF-8 source file contents
- `deploy_order`: deterministic ordering for multi-contract packages

Optional contract fields supported by hub importers include `default_chi`,
`deploy_default`, and extra metadata fields. Keep optional fields out unless
they are useful to deploy or understand that package.

## Version And Commit Pins

Package manifests describe immutable releases. When a package is imported into
the contracting hub, the importer stores:

- the manifest hash
- every contract source hash
- the package version
- optional source repo, commit, or tag metadata

Package-local manifests may omit `source.commit`; for manifests that live in the
same repo as their source, embedding the current commit would be awkward because
the commit changes when the manifest changes. When freezing a public hub release
from a specific repo state, record the owner-repo commit or tag in the hub
release metadata and keep the manifest hash plus per-contract source hashes as
the content integrity checks.

## Validation

Run the repo validator after editing any manifest or source file:

```bash
uv run python scripts/validate_contracts.py
```

The validator requires one `contract-bundle.json` per package, checks that every
`src/con_*.py` file is listed exactly once, and recomputes the stored SHA-256
hashes.
