# rules__silver_v5.1__subset_selection__2026-08

The 200 v5.1 papers parsed with
`extractors/rules/silver_v5.1__subset_selection__2026-08`.

**Superseded — prefer the `__idfix` sibling.** These were produced before a
parser bug was fixed and are missing 147 objects: distilled objects were keyed
by the first letter of their type, so proposition/problem collided with proof,
conjecture/claim with corollary, and algorithm with assumption, and one of each
colliding pair was silently dropped. Losses land almost entirely on
`proposition` (56), `algorithm` (32), `conjecture` (27), `problem` (21) and
`claim` (11).

Kept only so the two can be diffed. Do not cite counts from this directory.
