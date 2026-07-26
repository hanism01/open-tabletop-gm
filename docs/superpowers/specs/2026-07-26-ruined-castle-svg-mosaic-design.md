# Ruined Castle SVG Mosaic Design

## Purpose

Create a self-contained, wide stained-glass illustration of three adventurers
observing a ruined castle and goblin patrols from concealment in a forest.

## Composition

- Use a 16:9, 1200×675 viewBox.
- Frame the near foreground with dark trunks, branches, and shrubs.
- Place three distinct, back-facing adventurer silhouettes along the lower third:
  a hooded scout, a sword-bearing warrior, and a staff-bearing mage.
- Open a descending visual corridor between them toward a clearing.
- Make the ruined castle the central focal mass, with broken towers, collapsed
  walls, and an arched gate.
- Place several small goblin patrol silhouettes and amber lanterns along readable
  paths through the clearing.

## Art Direction

Use ominous twilight. Deep pine and near-black foreground glass frames cold violet
mountains and ruins. A restrained amber glow in the gate, windows, and goblin
lanterns provides the brightest accents. Heavy near-black leading defines every
major silhouette; internal Voronoi cells use lighter leading and tint-only color
variation.

## Rendering Method

The HTML contains a declarative, back-to-front `SHAPES` contract. A `?flat=1` URL
switch renders only the flat scene. The default renderer creates deterministic
jittered-grid Voronoi cells separately inside each shape's clip path, adds a
backing plate, and restores the heavy outline over the cells.

## Iteration Requirement

Perform and inspect at least six revisions:

1. Establish the three value masses and focal clearing.
2. Clarify the castle silhouette and ruined profile.
3. Improve adventurer poses, concealment, and depth.
4. Introduce per-shape mosaic density and check boundary integrity.
5. Tune lead weights, tint variation, and focal contrast.
6. Polish patrol readability, foliage framing, and final balance.

Each revision is syntax-checked, rendered over local HTTP, captured as a screenshot,
and assessed before the next change.

## Acceptance Criteria

- The party, forest concealment, descending clearing, ruined castle, and goblin
  patrols are identifiable without texture in flat mode.
- The composition has three clear depth/value masses and one brightest focal zone.
- Mosaic cells never determine scene boundaries and never use hue jitter.
- Randomness is deterministic; `Math.random()` is absent.
- The delivered default view is mosaic, while `?flat=1` remains available.
- At least six inspected revision screenshots exist.

