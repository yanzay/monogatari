"""Grammar catalog integrity (catches dangling prereqs, malformed IDs, etc.)."""
from __future__ import annotations
import re
import pytest


@pytest.fixture(scope="session")
def catalog_entries(catalog):
    return catalog["entries"]


def test_catalog_has_required_top_keys(catalog):
    for k in ("schema_version", "source_policy", "entries"):
        assert k in catalog, f"catalog missing top-level key: {k}"


def test_catalog_entries_have_required_fields(catalog_entries):
    required = {"id", "marker", "jlpt", "category", "title", "short",
                "sources", "source_count", "prerequisites", "disputed"}
    bad = []
    for e in catalog_entries:
        missing = required - set(e.keys())
        if missing:
            bad.append(f"{e.get('id','?')}: missing {sorted(missing)}")
    assert not bad, "\n  ".join(bad)


def test_catalog_id_format(catalog_entries):
    pat = re.compile(r"^N[1-5]_[a-z][a-z0-9_]*$")
    bad = [e["id"] for e in catalog_entries if not pat.match(e["id"])]
    assert not bad, f"Malformed catalog IDs: {bad}"


def test_catalog_no_duplicate_ids(catalog_entries):
    seen: dict[str, int] = {}
    for e in catalog_entries:
        seen[e["id"]] = seen.get(e["id"], 0) + 1
    dupes = [eid for eid, n in seen.items() if n > 1]
    assert not dupes, f"Duplicate catalog IDs: {dupes}"


def test_catalog_id_jlpt_consistent(catalog_entries):
    """ID prefix must match the declared jlpt field."""
    bad = []
    for e in catalog_entries:
        id_tier = e["id"][:2]
        if id_tier != e["jlpt"]:
            bad.append(f"{e['id']}: jlpt={e['jlpt']}")
    assert not bad, "\n  ".join(bad)


def test_catalog_jlpt_in_known_set(catalog_entries):
    valid = {"N1", "N2", "N3", "N4", "N5"}
    bad = [(e["id"], e["jlpt"]) for e in catalog_entries if e["jlpt"] not in valid]
    assert not bad, f"Invalid JLPT values: {bad}"


def test_catalog_source_count_matches_sources(catalog_entries):
    bad = []
    for e in catalog_entries:
        if e["source_count"] != len(e["sources"]):
            bad.append(f"{e['id']}: source_count={e['source_count']} but len(sources)={len(e['sources'])}")
    assert not bad, "\n  ".join(bad)


def test_catalog_min_two_sources(catalog_entries):
    """The whole point of the catalog is multi-source corroboration."""
    bad = [e["id"] for e in catalog_entries if e["source_count"] < 2]
    assert not bad, f"Single-source entries: {bad}"


def test_catalog_prerequisites_resolve(catalog_entries):
    """Catches the bug where 34 entries referenced N4_ta_form etc.
    (which don't exist; the actual ID is N5_ta_form).
    """
    all_ids = {e["id"] for e in catalog_entries}
    bad = []
    for e in catalog_entries:
        for p in e.get("prerequisites", []):
            if p not in all_ids:
                bad.append(f"{e['id']} requires {p}")
    assert not bad, "Unresolved catalog prerequisites:\n  " + "\n  ".join(bad)


def test_catalog_no_self_prerequisites(catalog_entries):
    bad = [e["id"] for e in catalog_entries if e["id"] in e.get("prerequisites", [])]
    assert not bad, f"Self-prerequisites: {bad}"


def test_catalog_prereq_tier_no_higher_than_self(catalog_entries):
    """A grammar point at tier N5 should not depend on an N4 point.
    (Easier tiers come first in the curriculum.)"""
    order = {"N5": 0, "N4": 1, "N3": 2, "N2": 3, "N1": 4}
    by_id = {e["id"]: e for e in catalog_entries}
    bad = []
    for e in catalog_entries:
        my_tier = order.get(e["jlpt"], 99)
        for p in e.get("prerequisites", []):
            if p in by_id:
                pt = order.get(by_id[p]["jlpt"], 99)
                if pt > my_tier:
                    bad.append(f"{e['id']} ({e['jlpt']}) requires {p} ({by_id[p]['jlpt']}) — harder prereq")
    assert not bad, "\n  ".join(bad)


def test_catalog_state_grammar_catalog_ids_resolve(grammar, catalog_entries):
    """Every grammar_state.points[*].catalog_id must point at a real catalog entry."""
    catalog_ids = {e["id"] for e in catalog_entries}
    bad = []
    for gid, p in grammar["points"].items():
        cid = p.get("catalog_id")
        if cid and cid not in catalog_ids:
            bad.append(f"{gid}.catalog_id={cid}")
    assert not bad, "grammar_state.catalog_id references unknown catalog entry:\n  " + "\n  ".join(bad)


def test_catalog_no_disputed_at_n5(catalog_entries):
    """N5 should be the most-agreed-on tier; flag any disputed N5 entries for re-review."""
    bad = [e["id"] for e in catalog_entries if e.get("disputed") and e["jlpt"] == "N5"]
    assert not bad, f"Disputed N5 entries (re-review needed): {bad}"
