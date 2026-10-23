"""Concept cards and the memory vault.  OWNER: AGENT (task L-11, DECISIONS L-2); the skip threshold is L-01 (O-1c).

Contract
--------
    Vault(root, *, now=None)
        .card(concept) -> ConceptCard | None
        .recall(concept) -> float              # 0.0 for a concept never reviewed
        .known(concepts) -> set[str]           # recall above KNOWN_RECALL
        .review(concept, rating, *, rule_id, why) -> ConceptCard
        .write_mistake(...) -> VaultNote
        .write_board(...) -> VaultNote
        .graph() -> {"nodes": [...], "links": [...]}
    default_vault_dir() -> Path                # REFLOW_VAULT, else ~/.reflow/vault

A plain folder of markdown notes the user can open in Obsidian (or Foam,
SilverBullet), on the user's machine only:

    concepts/<concept>.md     the concept's ConceptCard in its frontmatter; why it matters,
                              the rule that checks it, [[mistakes/...]] and [[boards/...]]
    mistakes/<date>-<board>-<concept>.md   what the AI's draft did, what the user answered,
                              the right part, the why and the fix
    boards/<board>.md         the request, parts, run, sign-off, [[concepts/...]], [[mistakes/...]]

One fsrs card per concept (fsrs 6.3.2). `review` takes the rating from what
the user did (L-01: good / hard / again), never from self-rating. A concept
whose recall is above KNOWN_RECALL (0.9) right now is skipped on the next
board, and the UI shows the skip.

Frontmatter values are written as JSON, which is valid YAML, so Obsidian shows
them as properties. A concept note's `## My notes` section is the user's and
is kept when reflow rewrites the note.

Must never
----------
- write outside the vault, or anywhere but the user's machine,
- rate a concept from anything but what the user did,
- drop the user's own notes when rewriting a note.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fsrs import Card, Rating, Scheduler

from reflow.contracts import ConceptCard, VaultNote

KNOWN_RECALL = 0.9
_RATINGS = {"good": Rating.Good, "hard": Rating.Hard, "again": Rating.Again}
_TITLES = {
    "pinout": "Pinouts",
    "decoupling": "Decoupling",
    "i2c-pullup": "I²C pull-ups",
    "address-strap": "Address straps",
    "led-current-limit": "LED current limit",
}
_FOLDERS = {"concepts": "concept", "mistakes": "mistake", "boards": "board"}
_LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
_MY_NOTES = "## My notes"


def default_vault_dir() -> Path:
    override = os.environ.get("REFLOW_VAULT", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".reflow" / "vault"


class Vault:
    def __init__(self, root, *, now=None) -> None:
        self.root = Path(root)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.scheduler = Scheduler()

    # --- cards -------------------------------------------------------------

    def card(self, concept: str) -> ConceptCard | None:
        meta = self._concept_meta(concept)
        if not meta.get("fsrs"):
            return None
        return ConceptCard(concept=concept, fsrs=meta["fsrs"], last_reviewed=meta.get("last_reviewed", ""),
                           ratings=list(meta.get("ratings", [])))

    def recall(self, concept: str) -> float:
        card = self.card(concept)
        if card is None:
            return 0.0
        return float(self.scheduler.get_card_retrievability(Card.from_dict(json.loads(card.fsrs)), self.now()))

    def known(self, concepts) -> set[str]:
        return {c for c in concepts if self.recall(c) > KNOWN_RECALL}

    def review(self, concept: str, rating: str, *, rule_id: str, why: str) -> ConceptCard:
        if rating not in _RATINGS:
            raise ValueError(f"rating must be one of {sorted(_RATINGS)}, got {rating!r}")
        meta = self._concept_meta(concept)
        when = self.now()
        previous = Card.from_dict(json.loads(meta["fsrs"])) if meta.get("fsrs") else Card()
        updated, _ = self.scheduler.review_card(previous, _RATINGS[rating], when)
        stamp = _stamp(when)
        meta.update(
            fsrs=json.dumps(updated.to_dict(), sort_keys=True),
            last_reviewed=stamp,
            ratings=list(meta.get("ratings", [])) + [f"{stamp} {rating}"],
            rule_ids=sorted(set(meta.get("rule_ids", [])) | {rule_id}),
            why=why or meta.get("why", ""),
        )
        self._write_concept(concept, meta)
        return self.card(concept)

    # --- notes -------------------------------------------------------------

    def write_mistake(self, *, board: str, concept: str, rule_id: str, found: str, answer: str,
                      right_refs: list[str], correct: bool, why: str, fix: str) -> VaultNote:
        stem = f"{_stamp(self.now())[:10]}-{_slug(board)}-{concept}"
        path, n = f"mistakes/{stem}.md", 2
        while (self.root / path).exists():
            path, n = f"mistakes/{stem}-{n}.md", n + 1
        title = f"{board}: {_TITLES.get(concept, concept)}"
        links = [f"concepts/{concept}", f"boards/{_slug(board)}"]
        meta = {"kind": "mistake", "title": title, "board": board, "concept": concept, "rule_id": rule_id,
                "correct": correct, "date": _stamp(self.now())}
        body = "\n".join([
            f"# {title}", "",
            f"**What the AI's draft did:** {found}", "",
            f"**You answered:** {answer or '(nothing)'} ({'right' if correct else 'not the part'})", "",
            f"**The part:** {', '.join(right_refs)}", "",
            f"**Why it matters:** {why}", "",
            f"**The fix:** {fix}", "",
            f"Concept: [[{links[0]}]] · Board: [[{links[1]}]]", "",
        ])
        self._write(path, meta, body)
        concept_meta = self._concept_meta(concept)
        concept_meta["mistakes"] = _add(concept_meta.get("mistakes", []), path[:-3])
        self._write_concept(concept, concept_meta)
        return VaultNote(path=path, kind="mistake", title=title, links=links)

    def write_board(self, *, board: str, request: str, run_dir: str, status: str, parts: list[str],
                    concepts: list[str], mistakes: list[str], signed_off: bool | None) -> VaultNote:
        path = f"boards/{_slug(board)}.md"
        old = _read_note(self.root / path)[0]
        concept_links = _add(old.get("concepts", []), *[f"concepts/{c}" for c in concepts])
        mistake_links = _add(old.get("mistakes", []), *[m[:-3] if m.endswith(".md") else m for m in mistakes])
        meta = {"kind": "board", "title": board, "request": request, "run_dir": run_dir, "status": status,
                "signed_off": signed_off, "concepts": concept_links, "mistakes": mistake_links}
        signed = {True: "yes", False: "no", None: "not yet"}[signed_off]
        body = "\n".join(
            [f"# {board}", "", f"**Request:** {request}", "", f"**Run:** `{run_dir}` · {status}", "",
             f"**Signed off:** {signed}", "", "## Parts", ""]
            + [f"- {p}" for p in parts] + ["", "## Concepts", ""]
            + [f"- [[{c}]]" for c in concept_links] + ["", "## Mistakes", ""]
            + [f"- [[{m}]]" for m in mistake_links] + [""]
        )
        self._write(path, meta, body)
        for concept in concepts:
            concept_meta = self._concept_meta(concept)
            concept_meta["boards"] = _add(concept_meta.get("boards", []), path[:-3])
            self._write_concept(concept, concept_meta)
        return VaultNote(path=path, kind="board", title=board, links=concept_links + mistake_links)

    def graph(self) -> dict:
        nodes, texts = [], {}
        for folder, kind in _FOLDERS.items():
            for note in sorted((self.root / folder).glob("*.md")):
                node_id = f"{folder}/{note.stem}"
                meta, body = _read_note(note)
                title = meta.get("title") or next((l[2:] for l in body.splitlines() if l.startswith("# ")), note.stem)
                nodes.append({"id": node_id, "kind": kind, "title": title, "path": f"{node_id}.md",
                              "obsidian": "obsidian://open?path=" + quote(str(note.resolve()), safe="")})
                texts[node_id] = note.read_text(encoding="utf-8")
        ids = set(texts)
        links = sorted({(source, target.strip()) for source, text in texts.items()
                        for target in _LINK.findall(text) if target.strip() in ids and target.strip() != source})
        return {"nodes": nodes, "links": [{"source": s, "target": t} for s, t in links]}

    # --- files -------------------------------------------------------------

    def _concept_meta(self, concept: str) -> dict:
        return _read_note(self.root / "concepts" / f"{concept}.md")[0]

    def _write_concept(self, concept: str, meta: dict) -> None:
        path = f"concepts/{concept}.md"
        mine = _my_notes(self.root / path)
        meta = {"kind": "concept", "title": _TITLES.get(concept, concept), "concept": concept, **{
            k: v for k, v in meta.items() if k not in ("kind", "title", "concept")}}
        rules = ", ".join(f"`{r}`" for r in meta.get("rule_ids", [])) or "—"
        body = "\n".join(
            [f"# {meta['title']}", "", f"**Checked by:** {rules}", "", f"**Why it matters:** {meta.get('why', '')}", "",
             f"**Reviews:** {len(meta.get('ratings', []))} (last: {meta.get('last_reviewed') or 'never'})", "",
             "## Mistakes", ""]
            + [f"- [[{m}]]" for m in meta.get("mistakes", [])] + ["", "## Boards", ""]
            + [f"- [[{b}]]" for b in meta.get("boards", [])] + ["", _MY_NOTES, "", mine]
        )
        self._write(path, meta, body)

    def _write(self, path: str, meta: dict, body: str) -> None:
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError(f"{path} is outside the vault")
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = ["---"] + [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in meta.items()] + ["---", ""]
        target.write_text("\n".join(lines) + body.rstrip("\n") + "\n", encoding="utf-8")


def _read_note(path: Path) -> tuple[dict, str]:
    """Frontmatter (JSON values; simple YAML lists and plain strings too, in case Obsidian rewrote it) and body."""
    if not path.is_file():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {}, text
    head, body = text[4:].split("\n---\n", 1)
    meta: dict = {}
    key = None
    for line in head.splitlines():
        item = re.match(r"\s+-\s+(.*)$", line)
        if item and key is not None:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(_value(item.group(1)))
            continue
        match = re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            key, raw = match.groups()
            meta[key] = _value(raw) if raw.strip() else []
    return meta, body


def _value(raw: str):
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        return raw.strip("'\"")


def _my_notes(path: Path) -> str:
    body = _read_note(path)[1]
    return body.split(_MY_NOTES, 1)[1].strip("\n") + "\n" if _MY_NOTES in body else ""


def _add(items: list[str], *new: str) -> list[str]:
    out = list(items)
    for item in new:
        if item not in out:
            out.append(item)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "board"


def _stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
