"""Write the raw KB v2.1 from KB v2 and its approved change table (DATA-06, DATA-17).

Usage, from the repository root:

    python3 -I data/raw/kb/v2.1/make_kb_v2_1.py data/raw/kb/v2.1/changes.json \
        data/raw/kb/v2 <new folder>/v2.1 [--approved]

The script reads KB v2 only, and writes `kb-release.json` and the KB file into a new folder named
by the KB version. Without `--approved` it is a dry run, and the table may still be a proposal;
with it, the `status` of the table must start with "approved". It prints every change.

It stops with exit status 1, before it writes anything, when:
- a file of KB v2 has another SHA-256 than the table records, or does not round-trip to its bytes;
- the table does not cover the release of KB v2, in its order, or names a document twice;
- a replacement does not occur exactly once in its field at its turn;
- a text of KB v2.1 still holds "tiki" in any case;
- a field other than the changed fields differs, or the text and the version do not change together.
It also stops when a file of KB v2 changed during the run.
"""

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

Record = dict[str, Any]

CHANGED_FIELDS = frozenset(
    {"title", "content", "version", "approved_at", "policy_key", "supported_intents", "content_hash"}
)
BRAND = re.compile(r"tiki", re.IGNORECASE)
RELEASE_FILE = "kb-release.json"
CONTEXT_WORDS = 3


def fail(message: str) -> None:
    """Print why the run stops and exit with status 1."""
    print(f"STOP: {message}", file=sys.stderr)
    sys.exit(1)


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file, in lowercase hexadecimal."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(value: object, final_newline: bool) -> str:
    """Write JSON as KB v2 does: two-space indents, UTF-8 text, and its final-newline style."""
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text + "\n" if final_newline else text


def read_round_trip(path: Path) -> tuple[Any, bool]:
    """Read a JSON file of KB v2 and check that it round-trips to the same bytes."""
    data = path.read_bytes()
    final_newline = data.endswith(b"\n")
    value = json.loads(data.decode("utf-8"))
    if dump(value, final_newline).encode("utf-8") != data:
        fail(f"{path.name} does not round-trip to the same bytes")
    return value, final_newline


def with_policy_key(record: Record, policy_key: str) -> Record:
    """Return the record with `policy_key` placed after `category`."""
    if "policy_key" in record or "category" not in record:
        fail(f"{record['document_id']}: cannot place policy_key after category")
    result: Record = {}
    for key, value in record.items():
        result[key] = value
        if key == "category":
            result["policy_key"] = policy_key
    return result


def changed_record(old: Record, change: Record) -> Record:
    """Apply one row of the change table to a record of KB v2."""
    document_id = change["document_id"]
    new = with_policy_key(dict(old), change["policy_key"])
    for replacement in change["replacements"]:
        field = replacement["field"]
        count = new[field].count(replacement["old"])
        if count != 1:
            fail(f"{document_id} {field}: {replacement['old']!r} occurs {count} times")
        new[field] = new[field].replace(replacement["old"], replacement["new"])
    if change["supported_intents"] is not None:
        new["supported_intents"] = change["supported_intents"]
    if change["approved_at"] is not None:
        new["approved_at"] = change["approved_at"]
    new["version"] = change["version"]
    new["content_hash"] = hashlib.sha256(new["content"].encode("utf-8")).hexdigest()
    text_changed = (old["title"], old["content"]) != (new["title"], new["content"])
    version_changed = change["version"] != change["from_version"]
    if text_changed != version_changed or version_changed != (change["approved_at"] is not None):
        fail(f"{document_id}: the text, the version, and approved_at must change together")
    if BRAND.search(json.dumps(new, ensure_ascii=False)):
        fail(f"{document_id} still holds the brand")
    for key in set(old) | set(new):
        if key not in CHANGED_FIELDS and old.get(key) != new.get(key):
            fail(f"{document_id}: field {key} changed")
    return new


def word_diff(old: str, new: str) -> list[str]:
    """Return each changed run of words, with the words before it."""
    old_words, new_words = old.split(" "), new.split(" ")
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    return [
        f"    ...{' '.join(old_words[max(0, i1 - CONTEXT_WORDS):i1])} "
        f"[-{' '.join(old_words[i1:i2])}-]{{+{' '.join(new_words[j1:j2])}+}}"
        for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        if tag != "equal"
    ]


def print_changes(pairs: list[tuple[Record, Record]], old_release: Record, new_release: Record) -> None:
    """Print every change of every record and of the release file."""
    for old, new in pairs:
        print(f"\n== {new['document_id']}: version {old['version']} -> {new['version']}")
        print(f"  policy_key: (absent) -> {new['policy_key']}")
        for field in ("supported_intents", "approved_at"):
            if old[field] != new[field]:
                print(f"  {field}: {old[field]} -> {new[field]}")
        for field in ("title", "content"):
            if old[field] != new[field]:
                print(f"  {field}:")
                print("\n".join(word_diff(old[field], new[field])))
        if old["content_hash"] != new["content_hash"]:
            print(f"  content_hash: {old['content_hash']} -> {new['content_hash']}")
    print(f"\n== {RELEASE_FILE}")
    for field in ("release", "source"):
        print(f"  {field}: {old_release[field]} -> {new_release[field]}")
    for old_entry, new_entry in zip(old_release["documents"], new_release["documents"], strict=True):
        if old_entry != new_entry:
            print(f"  {old_entry['document_id']}: {old_entry['version']} -> {new_entry['version']}")


def main() -> None:
    """Check the inputs, build KB v2.1, write it, and print the changes."""
    args = [arg for arg in sys.argv[1:] if arg != "--approved"]
    if len(args) != 3:
        fail("usage: make_kb_v2_1.py <changes.json> <v2 folder> <new output folder> [--approved]")
    changes_path, v2_folder, output = (Path(arg) for arg in args)
    changes = json.loads(changes_path.read_text(encoding="utf-8"))
    if "--approved" in sys.argv[1:] and not str(changes["status"]).startswith("approved"):
        fail(f"the change table is not approved: status {changes['status']!r}")
    if output.exists() or output.name != changes["kb_version"]:
        fail(f"the output folder must be new and named {changes['kb_version']}")

    base = changes["base"]
    release_path, kb_path = v2_folder / RELEASE_FILE, v2_folder / base["kb_file"]
    if (sha256_of(release_path), sha256_of(kb_path)) != (base["kb_release_sha256"], base["kb_file_sha256"]):
        fail("a file of KB v2 has another SHA-256 than the table records")
    old_release, release_newline = read_round_trip(release_path)
    old_records, kb_newline = read_round_trip(kb_path)

    by_id: dict[str, Record] = {record["document_id"]: record for record in old_records}
    rows = changes["documents"]
    table_pairs = [(row["document_id"], row["from_version"]) for row in rows]
    released_pairs = [(entry["document_id"], entry["version"]) for entry in old_release["documents"]]
    if len(by_id) != len(old_records) or table_pairs != released_pairs:
        fail("the table must cover the release of KB v2 once each, in its order")
    if any(by_id[document_id]["version"] != version for document_id, version in table_pairs):
        fail("a version of the table is not the version of KB v2")

    pairs = [(by_id[row["document_id"]], changed_record(by_id[row["document_id"]], row)) for row in rows]
    new_records = [new for _, new in pairs]
    new_release: Record = {
        "release": changes["release"]["release"],
        "source": changes["release"]["source"],
        "documents": [{"document_id": r["document_id"], "version": r["version"]} for r in new_records],
    }

    output.mkdir(parents=True)
    (output / changes["kb_file"]).write_text(dump(new_records, kb_newline), encoding="utf-8")
    (output / RELEASE_FILE).write_text(dump(new_release, release_newline), encoding="utf-8")
    if (sha256_of(release_path), sha256_of(kb_path)) != (base["kb_release_sha256"], base["kb_file_sha256"]):
        fail("a file of KB v2 changed during the run")

    left_out = sorted(set(by_id) - {document_id for document_id, _ in table_pairs})
    print(f"KB v2 records: {len(old_records)}; left out: {left_out}")
    print(f"KB {changes['kb_version']} records: {len(new_records)}")
    print_changes(pairs, old_release, new_release)
    for name in (changes["kb_file"], RELEASE_FILE):
        print(f"sha256 {sha256_of(output / name)}  {name}")


if __name__ == "__main__":
    main()
