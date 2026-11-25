# Synthetic normalization binding verification

Refs [#74 (CP-15.02)](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/74).
The [field-binding candidate](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/74#issuecomment-7152027265)
checks the complete set of normalization declarations before invoking the
normalizer. Its published test blob contains an unterminated string and cannot
be imported. The repair restores the intact predecessor test file and adds
the intended field-binding regression. The candidate adapter and fixture bytes
are preserved.

## Tested source

| Artifact | Git object |
| --- | --- |
| Historical composition | [`01cd1afa`](https://api.github.com/repos/Pick-Your-AI/pick-your-ai-catalog-pipeline/git/trees/01cd1afad45b606417ce13ff4b622a0fbbf16bca?recursive=1) |
| Published field-binding candidate | [`e8e50dcf`](https://api.github.com/repos/Pick-Your-AI/pick-your-ai-catalog-pipeline/git/trees/e8e50dcfb83ebd10161a7b59c77c2531bbcb880d?recursive=1) |
| Repaired composition | [`3df08f4f`](https://api.github.com/repos/synchronic1/pick-your-ai-catalog-pipeline/git/trees/3df08f4fb7680f9a50096a9bc3a2e9ea1150f166?recursive=1) |
| Adapter blob | `b3d4af3224ce2a10ca8a91eef26e1c4241489a84` |
| Repaired test blob | `b31618159e9e9670e6c269a777ac909fa5e3fe06` |

The repaired tree has 443 files. Its only differences from the historical
composition are `tests/integration/adapters.py` and
`tests/integration/test_pipeline.py`. The repaired tree is a detached Git
object on the contributor fork.

## Results

Python 3.12.14 on Linux, with all six validation dependency pins and an audit
hook denying Python socket operations.

| Check | Result |
| --- | --- |
| Compile the published candidate test | Fails at line 504 with an unterminated string |
| Run the repaired regression with the predecessor adapter | Fails, reproducing the missing gate |
| Run the repaired regression with the corrected adapter | Passes all six cases in both synthetic domains |
| Run the recovered integration module | 27 tests passed |
| Run planning, example and generated-document validators | All passed |

The regression covers duplicate declarations, an unrelated entity, an unrelated
normalization revision, an omitted field, an undeclared observation field and
an empty declaration set. Each case verifies that normalization never runs,
intake is the only transition recorded, no candidate or review state is
created, and the previously active release pointer and artifact hashes survive.
The recovered module also exercises successful delivery for both fixture domains.

## Reproduce the socket-denied run

Use Linux with Python 3.12.14 and an absolute `WHEELHOUSE` path containing
the six pinned dependencies. Source acquisition is the networked step.
After acquisition, the setup uses only local wheels and the test commands
run with the socket audit hook.

```sh
set -eu
scratch=$(mktemp -d)
tree=3df08f4fb7680f9a50096a9bc3a2e9ea1150f166
fork=https://github.com/synchronic1/pick-your-ai-catalog-pipeline.git
git -C "$scratch" init -q
git -C "$scratch" fetch --no-tags "$fork" "$tree"
test "$(git -C "$scratch" rev-parse FETCH_HEAD)" = "$tree"
test "$(git -C "$scratch" cat-file -t "$tree")" = tree
git -C "$scratch" archive --format=tar -o "$scratch/source.tar" "$tree"
mkdir "$scratch/source" "$scratch/hook"
tar -xf "$scratch/source.tar" -C "$scratch/source"
```

If the server refuses to fetch the tree by object ID, use a maintainer-provided
reachable ref and its independently recorded commit ID. Verify `FETCH_HEAD`
against that ID and `FETCH_HEAD^{tree}` against `$tree` before exporting.
For a maintainer-provided archive, verify its SHA-256 against the accompanying
manifest before extracting. Stage the extracted files in a fresh Git repository
with `core.autocrlf=false` and verify `git write-tree` returns `$tree`.
Resume only after the exact tree matches. These are fallback instructions.
The published object was fetched directly for this verification.

```sh
python3.12 -m venv "$scratch/venv"
py="$scratch/venv/bin/python"
"$py" -m pip install --no-index --find-links "$WHEELHOUSE" \
    -r "$scratch/source/requirements-validation.txt"
cat > "$scratch/hook/sitecustomize.py" <<'PY'
import sys

def deny_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("network disabled for synthetic integration verification")

sys.addaudithook(deny_network)
PY

cd "$scratch/source"
export PYTHONPATH="$scratch/hook" PYTHONDONTWRITEBYTECODE=1
unset PIPELINE_EVIDENCE_DIR
"$py" -m unittest tests.integration.test_pipeline -v
"$py" scripts/validate_plan.py
"$py" scripts/validate_examples.py
"$py" scripts/render_docs.py --check
```

The hook rejects Python `socket.*` audit events in interpreters that load
`sitecustomize`. It provides no OS-level egress controls for external programs.

This receipt covers the isolated synthetic composition. Integration against
`main` depends on accepted [acquisition and replay #21](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/21),
[release promotion #49](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/49) and
[producer-consumer acceptance #58](https://github.com/Pick-Your-AI/pick-your-ai-catalog-pipeline/issues/58).
The remaining #74 gates include independent review, source-rights and consumer
receipts, and operating acceptance.
