# Cloud experiment contract

The generic cloud bridge accepts a tracked experiment contract with
`--contract PATH`. The contract owns experiment identity; ignored
`.sktlm-bridge.toml` owns only operational SSH addresses, users, ports, keys,
and remote absolute paths.

The schema is `sktlm-cloud-experiment-contract/v1`. It declares:

- the exact Git branch;
- `git_remote` or `git_bundle` deployment and whether HEAD must be published;
- frozen input sets and their fixed validators;
- relative run and optional metrics roots;
- a fixed remote audit argv and inventory key;
- `report`, `scientific`, and `full` collection profiles;
- required audited files and the local collection root;
- an optional tracked host registry and/or exact workload-to-host-role rows;
- the completion schema expected from the experiment.

Absolute/traversing paths, secret-bearing keys, undeclared fields, duplicate
identities, unknown profiles, and unknown deployment transports fail closed.
The bridge refuses a local branch that differs from the contract.

For `git_remote`, `deploy-code` retains the clean, published, exact-HEAD and
fast-forward-only checks. For `git_bundle`, pass an already-created bundle:

```text
python scripts/cloud/sktlm_bridge.py \
  --contract configs/cloud/<experiment>.yaml \
  deploy-code --host-profile <role> \
  --bundle artifacts/deployment_bundles/<file>.bundle \
  --bundle-sha256 <sha256>
```

The bundle path is locally verified, must contain local HEAD, is transferred
only below the configured guarded data root, is verified remotely with both
SHA-256 and `git bundle verify`, and updates the named branch only by an exact
fast-forward. The workflow never fetches production code from GitHub when
`git_bundle` is selected.

Contract-driven input transfer validates every declared set before rsync,
uses resumable append verification without deletion, and reruns the declared
validators remotely. Contract-driven collection always audits first, resumes
only under an identical audit/host/profile identity, and compares downloaded
bytes and SHA-256 values to the declared remote inventory.
