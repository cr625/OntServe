# Upstream sources (pinned)

The candidate is extracted from these exact upstream releases. The raw OWL files
are archived in `sources/` so the build is offline-reproducible and version-locked.
To refresh, re-download from the URL and confirm the `versionIRI`; the SHA-256
detects any drift from the pinned release.

| Ontology | Download URL | versionIRI | SHA-256 | Fetched |
|----------|--------------|------------|---------|---------|
| BFO 2020 | http://purl.obolibrary.org/obo/bfo.owl | http://purl.obolibrary.org/obo/bfo/2019-08-26/bfo.owl | `ca399c2b8b79f4d12b296d5c4ea4c00940e1f82cee7d1a50ddc292aa4f6c4666` | 2026-06-30 |
| IAO | http://purl.obolibrary.org/obo/iao.owl | http://purl.obolibrary.org/obo/iao/2026-03-30/iao.owl | `c27ff2964a2ad8165bc365698b628aae95108411384aa4450e6e1b1e82bf0f41` | 2026-06-30 |
| RO | http://purl.obolibrary.org/obo/ro.owl | http://purl.obolibrary.org/obo/ro/releases/2025-12-17/ro.owl | `a9f644d4a865747e0b4aba7ca3f19aac1e0b072cab89e24a2e476df3abb10aaf` | 2026-06-30 |

Note: `bfo.owl` and `iao.owl` are the rolling-latest PURLs, which served the
releases above on the fetch date. Pin to the dated versionIRI PURL if a future
fetch must reproduce these exact files. Verify with:

    cd sources && sha256sum -c <<< "<hash>  bfo.owl"
