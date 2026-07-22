# System Module — Starfinder Second Edition

This module uses the Starfinder Second Edition rules, which share the Pathfinder Second Edition Remaster engine. Resolve rules from the campaign's books and character sheets first; this guide supplies the shared procedures the GM needs at the table.

---

## Dice Convention

**Core resolution:** Roll `d20 + modifier` against a Difficulty Class (DC), Armor Class (AC), or an opposing check. A modifier normally includes the relevant ability modifier, proficiency bonus, and any applicable circumstance, status, and item bonuses or penalties.

**Success thresholds:**

| Result | Degree of success |
|---|---|
| Total is at least 10 above the DC | Critical success |
| Total meets or exceeds the DC | Success |
| Total is 10 or more below the DC | Critical failure |
| Otherwise | Failure |

A natural 20 improves the degree of success by one step; a natural 1 worsens it by one step. Apply this adjustment after comparing the total to the DC. Do not treat a 20 as an automatic success or a 1 as an automatic failure when an adjustment leaves the degree unchanged.

Use the GM's level-based DC table or a published DC when available. For an opposed roll, compare the result to the opponent's relevant DC (such as Fortitude DC, Reflex DC, Will DC, or class DC) unless a rule explicitly calls for both parties to roll.

**Bonus rules:** Bonuses and penalties have types. For each type—circumstance, status, and item—use only the highest bonus and the worst penalty; untyped bonuses and penalties stack unless a rule says otherwise.

**Example inline combat narration:**
`Iseld fires her azimuth laser pistol at the corovan: d20+13 = 25 vs AC 21 — success. It deals 1d6+2 = 6 fire damage.`

---

## Ability Scores / Statistics

The six attributes are **Strength (STR), Dexterity (DEX), Constitution (CON), Intelligence (INT), Wisdom (WIS), and Charisma (CHA)**. Characters record the **raw attribute modifiers** (for example, DEX `+4`), not legacy ability scores. Ability boosts increase a modifier; a flaw decreases it, subject to the character-building rules.

| Stat | Governs |
|---|---|
| STR | Melee force, Athletics, bulk, many melee damage rolls |
| DEX | AC limits, Reflex saves, Stealth, finesse and ranged attacks |
| CON | Hit Points, Fortitude saves, endurance |
| INT | Computers, Crafting, Society, learned skills |
| WIS | Perception, Will saves, Medicine, Piloting awareness |
| CHA | Deception, Diplomacy, Intimidation, performance and force of personality |

**Proficiency:** A trained statistic adds the character's level plus a proficiency rank bonus: trained `+2`, expert `+4`, master `+6`, or legendary `+8`. Untrained checks add no proficiency bonus. This is the default proficiency-with-level rule; use the campaign's stated proficiency-without-level variant only when it has been deliberately chosen.

---

## Character Structure

| Field | Notes |
|---|---|
| Ancestry / Heritage / Background / Class / Level | Establishes starting choices, features, and advancement |
| HP / Max HP | Damage reduces current HP; ancestry and class determine the maximum |
| Resolve Points | Usually 0–3 or more by level; spent to power stamina recovery and key class abilities |
| AC / Speed / Perception / Class DC | Core defensive and exploration statistics |
| Attribute modifiers | The six raw modifiers above; there are no legacy ability-score values to derive |
| Proficiencies | Skills, attacks, armor, perception, saves, spellcasting, and class DC |
| Saves | Fortitude, Reflex, and Will |
| Focus Points / spell slots | Only for characters with the relevant abilities |
| Conditions and effects | Track persistent conditions, durations, and ongoing effects |
| Inventory / Bulk / credits | Track carried equipment, item levels, and capacity |
| XP or milestones | Use the campaign's advancement method |

---

## Health and Damage

Damage reduces current HP. Healing restores HP up to the character's maximum unless an effect says otherwise. Resistance reduces matching damage, weakness increases matching damage, and immunity prevents matching damage; apply the specific rule for the effect before reducing HP.

Temporary HP is a separate buffer: damage is taken from temporary HP first and does not stack with other temporary HP. When a creature receives temporary HP while it already has temporary HP with a different duration, it chooses whether to keep the existing temporary HP and duration or take the new temporary HP and duration. At 0 HP, follow the dying rules below rather than allowing the character to keep acting normally.

Persistent damage is a condition. At the end of each affected creature's turn, apply the persistent damage, then roll the listed flat check to end it; assistance and an appropriate action can improve the recovery chance when the rules allow.

---

## Primary Resource

**Resource name:** Resolve Points

**Range:** Typically 0–3 at low levels, increasing with level and class. Resolve Points are spent during play and refresh with rest as described below.

**Tracking:** Spend Resolve Points to power the abilities that call for them—chiefly recovering stamina or fueling class-specific stamina and focus effects—as defined by the character's class and feats. Track class resources—Focus Points, spell slots, and similar pools—separately on the character sheet. When a rule is uncertain, resolve the cost from the campaign's licensed source and record the ruling.

---

## Rests and Recovery

**Daily preparations:** After about 8 hours of rest, prepare spells, regain Focus Points through the relevant refocus activity when eligible, refresh Resolve Points, and refresh abilities that recover during daily preparations. A full night's rest restores HP equal to CON modifier (minimum 1) multiplied by level, subject to the campaign's circumstances.

**Treat Wounds:** A trained Medicine user can spend 10 minutes to attempt a Medicine check against the chosen Treat Wounds DC. On success, the target regains HP and its wounded condition is removed; on a critical success it removes wounded and regains the following HP. A creature is normally immune to Treat Wounds from **all healers** for 1 hour, subject to feats such as Continual Recovery.

| Medicine proficiency and DC | Success healing | Critical-success healing |
|---|---|---|
| Trained, DC 15 | 2d8 | 4d8 |
| Expert, DC 20 | 2d8 + 10 | 4d8 + 10 |
| Master, DC 30 | 2d8 + 30 | 4d8 + 30 |
| Legendary, DC 40 | 2d8 + 50 | 4d8 + 50 |

**Long-term recovery:** Use the Medicine activities, recovery checks, and downtime rules appropriate to the injury. `calendar.py rest short` can mark a 1-hour pause; `calendar.py rest long` can mark an 8-hour rest. Do not treat either command as automatic full healing.

---

## Incapacitation and Death

When a **PC or other significant creature** reaches 0 HP, it gains **dying 1**. It gains dying 2 instead if an attacker critically succeeded against it or it was reduced to 0 HP by a **critical failure on its own check**. Add its wounded value to that dying value. A creature with dying 4 dies (dying 5 if it has the Diehard feat). Ordinary NPCs and monsters generally die at 0 HP instead of using dying unless the GM marks them significant.

If nonlethal damage reduces a creature to 0 HP, it becomes unconscious at 0 HP instead of gaining dying. This nonlethal knockout is separate from the dying and wounded procedure.

When a creature gains dying, move its initiative position to directly before the turn during which it was reduced to 0 HP. This makes its recovery check occur before the source of the knockout acts again in subsequent rounds.

At the start of each turn while dying, attempt a recovery check: `d20` against DC `10 + dying value`.

| Recovery-check result | Effect |
|---|---|
| Critical success | Reduce dying by 2 |
| Success | Reduce dying by 1 |
| Failure | Increase dying by 1 |
| Critical failure | Increase dying by 2 |

Whenever a creature loses the dying condition, it gains **wounded 1**, or increases its wounded value by 1 if it already had it. Receiving healing while dying restores HP and removes dying; being reduced to 0 HP again becomes more dangerous because wounded is added to the new dying value.

---

## Status Effects / Conditions

Use `tracker.py condition add <name> <condition>` for active conditions. For a timed effect, use the exact tracker syntax `python3 scripts/tracker.py -c "$CAMPAIGN" effect start "$ENTITY" "<effect name>" <duration>` (for example, duration `3r`, `10m`, `8h`, or `indef`). Include the condition value where one matters.

| Condition | Severity | Effect summary |
|---|---|---|
| dying | danger | At 0 HP; make recovery checks and die at dying 4 unless an exception applies |
| unconscious | danger | Cannot act, is off-guard, and typically falls prone |
| doomed | danger | Lowers the dying value at which the creature dies |
| persistent damage | danger | Takes listed damage at turn end until a flat check ends it |
| wounded | warn | Added to dying when reduced to 0 HP |
| drained | warn | Lowers maximum HP and weakens Fortitude checks |
| fatigued | warn | Takes penalties to AC and saves and cannot use exploration activities requiring concentration |
| frightened | warn | Status penalty equal to its value; decreases at turn end |
| sickened | warn | Status penalty equal to its value; must retch to reduce it |
| clumsy / enfeebled / stupefied | warn | Penalty to DEX / STR / INT-WIS-CHA based checks and DCs respectively |
| slowed | warn | Loses actions equal to its value at the start of a turn |
| grabbed / restrained | info | Limits movement and imposes off-guard; restrained is the stronger state |
| off-guard | info | Takes a −2 circumstance penalty to AC |
| prone | info | On the ground; must Stand to rise and is off-guard to melee attacks |
| concealed / hidden / undetected | info | Limits targeting and requires the appropriate flat check or Seek action |
| quickened | buff | Gains the extra action specified by the effect |

---

## Advancement

Characters normally advance from level 1 to 20. At each level, apply the class's HP increase and the choices prescribed by ancestry, class, skill, and general feat progression. Ability boosts occur at levels 1, 5, 10, 15, and 20.

For XP campaigns, award XP for encounters, accomplishments, exploration, and story goals; 1,000 XP advances a character by one level. Milestone advancement is equally valid when the campaign uses it—advance the party together at meaningful story thresholds.

---

## Bold Play Reward

**Reward name:** Resolve Point

**Effect:** A Resolve Point powers stamina recovery and class abilities that consume it, as defined by the character's class and feats.

**How to award:** Resolve Points refresh with rest rather than being handed out for roleplay, but the GM may grant a bonus point or refresh for meaningful heroism, inventive problem-solving, or accepting dramatic consequences when the campaign uses that option. State why it was awarded and enforce the character's maximum.

---

## Campaign Arc Preferences

**Preferred campaign mode:** Either improvised or imported.

**Typical arc structure:** Dynamic faction-driven arcs fit home campaigns well; imported Adventure Paths often use structured hub-and-spoke chapters with level-appropriate milestones. Starship travel between planets and stations lends itself naturally to hub-and-spoke exploration.

**Genre conventions:** Starfinder assumes capable, increasingly legendary heroes in a science-fantasy galaxy. Let investigation, negotiation, exploration, starship operations, and tactical combat all matter; telegraph severe threats and give players information that lets them choose preparation, retreat, or a bold response.

---

## Additional System Notes

### Encounter Procedure and Action Economy

An encounter round gives every creature a turn in initiative order. On its turn, a creature normally has **three actions** and **one reaction**; free actions do not consume actions. A creature can take most actions in any order, but must meet each action's requirements. Reactions are triggered outside the creature's turn and are normally limited to one per round; some abilities grant additional reactions with specific limits.

Common actions include Strike, Stride, Step, Raise a Shield, Interact, Seek, Recall Knowledge, Demoralize, Aid, Cast a Spell, and Sustain. A spell's action icons determine whether it needs one, two, or three actions. Reactions and triggered abilities must be declared when their trigger occurs—do not retroactively add them after resolution.

Each Strike after the first in a turn takes the multiple attack penalty (MAP): usually −5 on the second attack and −10 on the third and later attacks. Apply weapon traits, agile reductions, and abilities that alter MAP. MAP applies to **all checks with the attack trait**, not only Strike attack rolls.

### Ranged and Area Attacks

**Ranged attacks** use a `d20 + modifier` Strike against the target's AC, applying DEX and proficiency. Beyond a weapon's first range increment, apply a cumulative −2 range penalty for each additional increment out to the weapon's maximum range. Firing in melee, cover, concealment, and the volley trait can all modify the roll; apply them before comparing to AC. Many Starfinder ranged weapons consume charges or ammunition and use the reload trait—track expended ammunition and reload actions.

**Area attacks** (bursts, cones, lines, and emanations) affect every creature in the described area. Each target attempts the listed **basic save** (typically Reflex) against the effect's DC: critical success takes no damage, success takes half, failure takes full, and critical failure takes double. Resolve the save's degree of success individually per target, then apply resistances, weaknesses, and immunities.

### Item Levels, Technology, and Credits

Every piece of equipment has an **item level** that gauges its power, price, and the proficiency needed to use it well. Wealth is tracked in **credits**. Technological gear—weapons, armor, computers, augmentations, and gadgets—often carries usage traits such as capacity, charges, and reload; track these like any other consumable resource. Computers and hacking use the relevant skill checks against the device or system DC. When a specific item's statistics are uncertain, look them up in the dataset below or resolve them from the campaign's licensed source and record the ruling.

### Spellcasting

Spellcasting follows the shared engine: spells have a rank, action cost shown by their action icons, and are cast from spell slots or as focus spells using Focus Points. Attack-roll spells compare `d20 + spell attack modifier` to AC; save-based spells force the target to roll against the caster's spell DC using the four degrees of success. Techno-magical and mystic traditions both use this framework. Track expended spell slots and Focus Points separately from Resolve Points.

### System Data Commands

When the SF2e data tools are installed, use these commands to build, synchronize, and retrieve rules rather than relying on memory:

```text
python3 systems/sf2e/lookup.py item "azimuth laser pistol"
python3 systems/sf2e/sync_foundry.py --check
```

```bash
python3 systems/sf2e/build_foundry.py
python3 systems/sf2e/sync_foundry.py
python3 systems/sf2e/lookup.py action "Aid"
```

`build_foundry.py` builds the local lookup dataset from the supported Foundry source. `sync_foundry.py --check` reports whether it is stale without changing it; `sync_foundry.py` refreshes it. The quoted lookup command retrieves a record by name from the SF2e dataset only. If those optional tools or data files are absent, use the campaign's licensed source material and record any table ruling.

### Table Rulings

Apply the four degrees of success every time a check has a DC. Announce the relevant action cost, MAP, reactions, and condition values before they become surprises. When a rule is uncertain, make a consistent temporary ruling, mark it for post-session lookup, and do not halt the encounter.
