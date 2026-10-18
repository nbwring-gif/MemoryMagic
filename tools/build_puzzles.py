#!/usr/bin/env python3
"""Convert Neal's puzzle CSV into the minified puzzles.json the app ships.

Usage:
    tools/build_puzzles.py puzzles/MM-test-puzzles-fixed.csv -o MentalMagic/Content/Resources/puzzles.json

Validates every row against the same rules the app applies (02-puzzle-file-format.md)
and refuses to write the file if anything fails, reporting problems by CSV row
number. Validation includes re-computing each step from its written wording, so
the arithmetic is checked rather than trusted.

`op` fields are deliberately not emitted: they are not in the CSV, and each step
already carries its `result`, so new wordings need no app update.
"""

import argparse
import csv
import datetime
import json
import re
import sys
from collections import Counter
from fractions import Fraction

MAX_TEXT = 60
STEPS = 9
CHOICES = 9

# Number words used in the fraction wordings, e.g. "THREE EIGHTHS OF IT".
NUMERATORS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4,
              "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8}
DENOMINATORS = {"HALF": 2, "THIRD": 3, "THIRDS": 3, "QUARTER": 4, "QUARTERS": 4,
                "FIFTH": 5, "FIFTHS": 5, "SIXTH": 6, "SIXTHS": 6,
                "SEVENTH": 7, "SEVENTHS": 7,
                # Neal's file contains both spellings.
                "EIGTH": 8, "EIGTHS": 8, "EIGHTH": 8, "EIGHTHS": 8}


class Unparsed(Exception):
    """The step wording is not in the vocabulary yet."""


def evaluate(text, x):
    """Apply a written step to `x`, exactly. Returns a Fraction."""
    t = " ".join(text.strip().upper().split())
    m = None

    def match(pattern):
        nonlocal m
        m = re.fullmatch(pattern, t)
        return m

    def first_group():
        return next(v for v in m.groups() if v is not None)

    if match(r"(\d+) MORE|ADD (\d+)|INCREASE BY (\d+)"):
        return x + int(first_group())
    if match(r"REDUCE BY (\d+)|REMOVE (\d+)|SUBTRACT (\d+)"):
        return x - int(first_group())
    if t == "DOUBLE IT":
        return 2 * x
    if t == "TRIPLE IT":
        return 3 * x
    if t in ("HALF OF IT", "HALVE IT"):
        return Fraction(x, 2)
    if t in ("IT SQUARED", "MULTIPLY IT BY ITSELF", "TIMES ITSELF"):
        return x * x
    if match(r"MULTIPLY BY (\d+(?:\.\d+)?)|X (\d+(?:\.\d+)?)"):
        return x * Fraction(first_group())
    if match(r"[/÷] ?(\d+)|DIVIDE BY (\d+)"):
        return Fraction(x, int(first_group()))
    if match(r"(\d+)/(\d+) OF (?:IT|THIS)"):
        return x * Fraction(int(m[1]), int(m[2]))
    if match(r"(\d+)% OF (?:IT|ITSELF)"):
        return x * Fraction(int(m[1]), 100)
    if match(r"(\d+) (\d+)/(\d+)% OF IT"):
        return x * (int(m[1]) + Fraction(int(m[2]), int(m[3]))) / 100
    if match(r"(\d+) (\d+)/(\d+) TIMES THIS"):
        return x * (int(m[1]) + Fraction(int(m[2]), int(m[3])))
    if match(r"ADD (\d+)% OF IT"):
        return x * (1 + Fraction(int(m[1]), 100))
    if match(r"LESS (\d+)%"):
        return x * (1 - Fraction(int(m[1]), 100))
    if match(r"(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN) (\w+) OF IT"):
        return x * Fraction(NUMERATORS[m[1]], DENOMINATORS[m[2]])
    raise Unparsed(text)


def read_int(row, column, label, row_number, problems):
    try:
        return int(row[column])
    except (KeyError, TypeError, ValueError):
        problems.append(f"row {row_number}: {label} is not an integer ({row.get(column)!r})")
        return None


def convert(csv_path):
    """Returns (puzzles, problems). Puzzles is empty if anything failed."""
    problems = []
    puzzles = []
    seen_ids = {}

    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            puzzle_id = (row.get("id") or "").strip()
            if not puzzle_id:
                problems.append(f"row {row_number}: missing id")
                continue
            if puzzle_id in seen_ids:
                problems.append(
                    f"row {row_number}: id {puzzle_id} already used on row {seen_ids[puzzle_id]}")
                continue
            seen_ids[puzzle_id] = row_number

            level = read_int(row, "level", "level", row_number, problems)
            start = read_int(row, "start", "start", row_number, problems)
            answer = read_int(row, "answer", "answer", row_number, problems)
            if level is None or start is None or answer is None:
                continue
            if level not in (1, 2, 3):
                problems.append(f"row {row_number}: level {level} is not 1, 2 or 3")
                continue

            steps = []
            value = Fraction(start)
            ok = True
            for index in range(1, STEPS + 1):
                text = (row.get(f"step{index}_text") or "").strip()
                result = read_int(row, f"step{index}_result",
                                  f"step{index}_result", row_number, problems)
                if not text:
                    problems.append(f"row {row_number}: step {index} has empty text")
                    ok = False
                    break
                if len(text) > MAX_TEXT:
                    problems.append(
                        f"row {row_number}: step {index} text is {len(text)} characters "
                        f"(max {MAX_TEXT})")
                    ok = False
                    break
                if result is None:
                    ok = False
                    break

                try:
                    computed = evaluate(text, value)
                except Unparsed:
                    problems.append(
                        f"row {row_number}: step {index} wording not understood: {text!r} "
                        "- add it to evaluate()")
                    ok = False
                    break
                if computed != result:
                    problems.append(
                        f"row {row_number}: step {index} {text!r} on {value} gives "
                        f"{computed}, but the file says {result}")
                    ok = False
                    break

                steps.append({"text": text, "result": result})
                value = Fraction(result)
            if not ok:
                continue

            if steps[-1]["result"] != answer:
                problems.append(
                    f"row {row_number}: answer {answer} does not match step 9 "
                    f"result {steps[-1]['result']}")
                continue

            choices = []
            for index in range(1, CHOICES + 1):
                choice = read_int(row, f"choice{index}", f"choice{index}",
                                  row_number, problems)
                if choice is None:
                    ok = False
                else:
                    choices.append(choice)
            if not ok:
                continue
            if len(set(choices)) != CHOICES:
                problems.append(f"row {row_number}: choices are not {CHOICES} unique values")
                continue
            if answer not in choices:
                problems.append(f"row {row_number}: answer {answer} is not among the choices")
                continue

            puzzles.append({
                "id": puzzle_id,
                "level": level,
                "start": start,
                "steps": steps,
                "answer": answer,
                "choices": choices,
            })

    return ([], problems) if problems else (puzzles, [])


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--version", type=int,
                        help="puzzle set version; defaults to one more than the "
                             "existing output file's")
    parser.add_argument("--pretty", action="store_true",
                        help="indent the JSON (the shipped file is minified)")
    args = parser.parse_args()

    puzzles, problems = convert(args.csv_path)
    if problems:
        print(f"{len(problems)} problem(s); nothing written:", file=sys.stderr)
        for problem in problems[:50]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > 50:
            print(f"  ... and {len(problems) - 50} more", file=sys.stderr)
        return 1

    version = args.version
    if version is None:
        try:
            with open(args.output, encoding="utf-8") as handle:
                version = json.load(handle).get("version", 0) + 1
        except (OSError, ValueError):
            version = 1

    document = {
        "schemaVersion": 1,
        "version": version,
        "updated": datetime.date.today().isoformat(),
        "puzzles": puzzles,
    }

    with open(args.output, "w", encoding="utf-8") as handle:
        if args.pretty:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")

    per_level = Counter(p["level"] for p in puzzles)
    size_mb = round(len(json.dumps(document, separators=(",", ":"))) / 1_048_576, 2)
    print(f"wrote {args.output}: version {version}, {len(puzzles)} puzzles "
          f"({', '.join(f'L{k}: {per_level[k]}' for k in sorted(per_level))}), ~{size_mb} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
