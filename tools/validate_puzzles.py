#!/usr/bin/env python3
"""Validate a puzzles.json against the same rules the app applies.

Usage:
    tools/validate_puzzles.py puzzles.json

Exits non-zero and lists the problems if the file would be rejected, so a
broken file never reaches players (development spec §6.1). The app silently
skips invalid puzzles; this refuses the whole file, because a published file
should have none.

Checks (02-puzzle-file-format.md):
  - schemaVersion is supported and version is a positive integer
  - ids are unique; level is 1, 2 or 3
  - exactly 9 steps and 9 unique choices, with the answer among them
  - the answer equals step 9's result
  - step text is non-empty and at most 60 characters
  - at least one puzzle per level
  - every step recomputes from its wording (shared with build_puzzles.py)
"""

import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_puzzles import CHOICES, MAX_TEXT, STEPS, Unparsed, evaluate  # noqa: E402

SUPPORTED_SCHEMA = 1


def validate(document):
    problems = []

    if document.get("schemaVersion") != SUPPORTED_SCHEMA:
        problems.append(
            f"schemaVersion is {document.get('schemaVersion')!r}, expected {SUPPORTED_SCHEMA}")

    version = document.get("version")
    if not isinstance(version, int) or version < 1:
        problems.append(f"version must be a positive integer, got {version!r}")

    puzzles = document.get("puzzles")
    if not isinstance(puzzles, list) or not puzzles:
        problems.append("puzzles must be a non-empty list")
        return problems

    seen_ids = {}
    per_level = Counter()

    for index, puzzle in enumerate(puzzles):
        where = f"puzzle {index} (id {puzzle.get('id')!r})"

        puzzle_id = puzzle.get("id")
        if not isinstance(puzzle_id, str) or not puzzle_id:
            problems.append(f"{where}: id must be a non-empty string")
        elif puzzle_id in seen_ids:
            problems.append(f"{where}: id already used by puzzle {seen_ids[puzzle_id]}")
        else:
            seen_ids[puzzle_id] = index

        level = puzzle.get("level")
        if level not in (1, 2, 3):
            problems.append(f"{where}: level {level!r} is not 1, 2 or 3")
        else:
            per_level[level] += 1

        start = puzzle.get("start")
        answer = puzzle.get("answer")
        if not isinstance(start, int) or not isinstance(answer, int):
            problems.append(f"{where}: start and answer must be integers")
            continue

        steps = puzzle.get("steps")
        if not isinstance(steps, list) or len(steps) != STEPS:
            problems.append(f"{where}: expected {STEPS} steps, found "
                            f"{len(steps) if isinstance(steps, list) else 'none'}")
            continue

        value = Fraction(start)
        step_ok = True
        for number, step in enumerate(steps, start=1):
            text = step.get("text")
            result = step.get("result")
            if not isinstance(text, str) or not text.strip():
                problems.append(f"{where}: step {number} has empty text")
                step_ok = False
                break
            if len(text) > MAX_TEXT:
                problems.append(f"{where}: step {number} text is {len(text)} "
                                f"characters (max {MAX_TEXT})")
                step_ok = False
                break
            if not isinstance(result, int):
                problems.append(f"{where}: step {number} result must be an integer")
                step_ok = False
                break

            try:
                computed = evaluate(text, value)
            except Unparsed:
                problems.append(f"{where}: step {number} wording not understood: "
                                f"{text!r} - add it to evaluate() in build_puzzles.py")
                step_ok = False
                break
            if computed != result:
                problems.append(f"{where}: step {number} {text!r} on {value} gives "
                                f"{computed}, but the file says {result}")
                step_ok = False
                break
            value = Fraction(result)

        if not step_ok:
            continue

        if steps[-1]["result"] != answer:
            problems.append(f"{where}: answer {answer} does not match step 9 "
                            f"result {steps[-1]['result']}")

        choices = puzzle.get("choices")
        if not isinstance(choices, list) or len(choices) != CHOICES:
            problems.append(f"{where}: expected {CHOICES} choices")
        elif len(set(choices)) != CHOICES:
            problems.append(f"{where}: choices are not unique")
        elif answer not in choices:
            problems.append(f"{where}: answer {answer} is not among the choices")

    # The app refuses a set it cannot deal every level from (§6).
    for level in (1, 2, 3):
        if per_level[level] == 0:
            problems.append(f"no valid puzzles at level {level}")

    return problems


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"could not read {path}: {error}", file=sys.stderr)
        return 1

    problems = validate(document)
    if problems:
        print(f"{len(problems)} problem(s) in {path}:", file=sys.stderr)
        for problem in problems[:50]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more", file=sys.stderr)
        return 1

    per_level = Counter(p["level"] for p in document["puzzles"])
    print(f"{path} is valid: version {document['version']}, "
          f"{len(document['puzzles'])} puzzles "
          f"({', '.join(f'L{k}: {per_level[k]}' for k in sorted(per_level))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
