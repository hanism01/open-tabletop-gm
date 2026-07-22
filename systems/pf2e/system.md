# System Module — Pathfinder Second Edition Remaster

This module uses the Pathfinder Second Edition Remaster rules. Resolve rules from the campaign's books and character sheets first; this guide supplies the shared procedures the GM needs at the table.

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
`Nhalia Strikes the cultist: d20+12 = 24 vs AC 22 — success. Her rapier deals 1d6+4 = 8 piercing damage.`

---

## Ability Scores / Statistics

The six ability scores are **Strength (STR), Dexterity (DEX), Constitution (CON), Intelligence (INT), Wisdom (WIS), and Charisma (CHA)**. Their modifiers are `(score − 10) ÷ 2`, rounded down.

| Stat | Governs |
|---|---|
| STR | Melee force, Athletics, bulk, many melee damage rolls |
| DEX | AC limits, Reflex saves, Stealth, finesse and ranged attacks |
| CON | Hit Points, Fortitude saves, endurance |
| INT | Arcana, Crafting, Society, learned skills |
| WIS | Perception, Will saves, Medicine, awareness |
| CHA | Deception, Diplomacy, Intimidation, performance and force of personality |

**Proficiency:** A trained statistic adds the character's level plus a proficiency rank bonus: trained `+2`, expert `+4`, master `+6`, or legendary `+8`. Untrained checks add no proficiency bonus. This is the default proficiency-with-level rule; use the campaign's stated proficiency-without-level variant only when it has been deliberately chosen.

---

## Character Structure

| Field | Notes |
|---|---|
| Ancestry / Heritage / Background / Class / Level | Establishes starting choices, features, and advancement |
| HP / Max HP | Damage reduces current HP; ancestry and class determine the maximum |
| Hero Points | Usually 0–3; a session begins with 1 unless the GM states otherwise |
| AC / Speed / Perception / Class DC | Core defensive and exploration statistics |
| Ability modifiers | The six ability modifiers above |
| Proficiencies | Skills, attacks, armor, perception, saves, spellcasting, and class DC |
| Saves | Fortitude, Reflex, and Will |
| Focus Points / spell slots | Only for characters with the relevant abilities |
| Conditions and effects | Track persistent conditions, durations, and ongoing effects |
| Inventory / Bulk / currency | Track carried equipment and capacity |
| XP or milestones | Use the campaign's advancement method |

---

## Health and Damage

Damage reduces current HP. Healing restores HP up to the character's maximum unless an effect says otherwise. Resistance reduces matching damage, weakness increases matching damage, and immunity prevents matching damage; apply the specific rule for the effect before reducing HP.

Temporary HP is a separate buffer: damage is taken from temporary HP first, does not stack with other temporary HP, and the larger amount replaces a smaller amount. At 0 HP, follow the dying rules below rather than allowing the character to keep acting normally.

Persistent damage is a condition. At the end of each affected creature's turn, apply the persistent damage, then roll the listed flat check to end it; assistance and an appropriate action can improve the recovery chance when the rules allow.

---

## Primary Resource

**Resource name:** Hero Points

**Range:** 0–3. At the start of a session each PC normally has 1 Hero Point. Award another for heroic, clever, or character-defining play; a PC cannot hold more than 3.

**Tracking:** Spend 1 Hero Point to reroll a check and use the new result. Spend all remaining Hero Points (minimum 1) when you would gain the dying condition to avoid dying: you instead remain at 0 HP, are stabilized, and do not increase wounded. Track class resources—Focus Points, spell slots, reagents, and similar pools—separately on the character sheet.

---

## Rests and Recovery

**Daily preparations:** After about 8 hours of rest, prepare spells, regain Focus Points through the relevant refocus activity when eligible, and refresh abilities that recover during daily preparations. A full night's rest restores HP equal to CON modifier (minimum 1) multiplied by level, subject to the campaign's circumstances.

**Treat Wounds:** A trained Medicine user can spend 10 minutes to attempt a Medicine check against the chosen Treat Wounds DC. On success, the target regains HP; on a critical success it regains double HP. A creature is normally immune to that healer's Treat Wounds for 1 hour, subject to feats such as Continual Recovery.

**Long-term recovery:** Use the Medicine activities, recovery checks, and downtime rules appropriate to the injury. `calendar.py rest short` can mark a 1-hour pause; `calendar.py rest long` can mark an 8-hour rest. Do not treat either command as automatic full healing.

---

## Incapacitation and Death

At 0 HP, a creature gains **dying 1**; if the effect was a critical success against it, it gains dying 2 instead. Add its wounded value to that dying value. A creature with dying 4 dies (dying 5 if it has the Diehard feat).

At the start of each turn while dying, attempt a recovery check: `d20` against DC `10 + dying value`.

| Recovery-check result | Effect |
|---|---|
| Critical success | Reduce dying by 2 |
| Success | Reduce dying by 1 |
| Failure | Increase dying by 1 |
| Critical failure | Increase dying by 2 |

When dying reaches 0, the creature is unconscious at 0 HP and gains **wounded 1**, or increases its wounded value by 1 if it already had it. Receiving healing while dying restores HP, removes dying, and leaves the creature wounded; being reduced to 0 HP again becomes more dangerous because wounded is added to the new dying value. A creature at 0 HP can spend all Hero Points to avoid gaining dying as described above.

---

## Status Effects / Conditions

Use `tracker.py condition add <name> <condition>` for active conditions and `tracker.py effect add` for timed effects. Include the condition value where one matters.

| Condition | Severity | Effect summary |
|---|---|---|
| dying | critical | At 0 HP; make recovery checks and die at dying 4 unless an exception applies |
| unconscious | critical | Cannot act, is off-guard, and typically falls prone |
| doomed | critical | Lowers the dying value at which the creature dies |
| persistent damage | critical | Takes listed damage at turn end until a flat check ends it |
| wounded | warn | Added to dying when reduced to 0 HP |
| drained | warn | Lowers maximum HP and weakens Fortitude checks |
| fatigued | warn | Takes penalties to AC and saves and cannot use exploration activities requiring concentration |
| frightened | warn | Status penalty equal to its value; decreases at turn end |
| sickened | warn | Status penalty equal to its value; must retch to reduce it |
| clumsy / enfeebled / stupefied | warn | Penalty to DEX / STR / INT-WIS-CHA based checks and DCs respectively |
| grabbed / restrained | info | Limits movement and imposes off-guard; restrained is the stronger state |
| off-guard | info | Takes a −2 circumstance penalty to AC |
| prone | info | On the ground; must Stand to rise and is off-guard to melee attacks |
| concealed / hidden / undetected | info | Limits targeting and requires the appropriate flat check or Seek action |
| quickened | buff | Gains the extra action specified by the effect |
| slowed | warn | Loses actions equal to its value at the start of a turn |

---

## Advancement

Characters normally advance from level 1 to 20. At each level, apply the class's HP increase and the choices prescribed by ancestry, class, skill, and general feat progression. Ability boosts occur at levels 1, 5, 10, 15, and 20.

For XP campaigns, award XP for encounters, accomplishments, exploration, and story goals; 1,000 XP advances a character by one level. Milestone advancement is equally valid when the campaign uses it—advance the party together at meaningful story thresholds.

---

## Bold Play Reward

**Reward name:** Hero Point

**Effect:** A Hero Point rerolls a check, or all remaining Hero Points can prevent dying as described above.

**How to award:** Award promptly for meaningful heroism, inventive problem-solving, accepting dramatic consequences, or playing a character's values and flaws in a way that makes the table better. State why it was awarded and enforce the three-point maximum.

---

## Campaign Arc Preferences

**Preferred campaign mode:** Either improvised or imported.

**Typical arc structure:** Dynamic faction-driven arcs fit home campaigns well; imported Adventure Paths often use structured hub-and-spoke chapters with level-appropriate milestones.

**Genre conventions:** Pathfinder assumes capable, increasingly legendary heroes. Let investigation, negotiation, exploration, and tactical combat all matter; telegraph severe threats and give players information that lets them choose preparation, retreat, or a bold response.

---

## Additional System Notes

### Encounter Procedure and Action Economy

An encounter round gives every creature a turn in initiative order. On its turn, a creature normally has **three actions** and **one reaction**; free actions do not consume actions. A creature can take most actions in any order, but must meet each action's requirements. Reactions are triggered outside the creature's turn and are normally limited to one per round; some abilities grant additional reactions with specific limits.

Common actions include Strike, Stride, Step, Raise a Shield, Interact, Seek, Recall Knowledge, Demoralize, Aid, Cast a Spell, and Sustain. A spell's action icons determine whether it needs one, two, or three actions. Reactions and triggered abilities must be declared when their trigger occurs—do not retroactively add them after resolution.

Each Strike after the first in a turn takes the multiple attack penalty (MAP): usually −5 on the second attack and −10 on the third and later attacks. Apply weapon traits, agile reductions, and abilities that alter MAP. MAP applies to attack rolls, not every action with the attack trait when a specific rule says otherwise.

### Aid

To **Aid**, prepare to help using an action on your turn and describe how you will assist. When the triggering ally attempts the relevant check, use your reaction and roll the appropriate check against the Aid DC (normally 15). On a critical success grant a +2 circumstance bonus; on a success grant +1; on a critical failure impose −1. Some feats improve these values.

### System Data Commands

When the PF2e data tools are installed, use these commands to retrieve rules rather than relying on memory:

```bash
python3 systems/pf2e/lookup.py action aid
python3 systems/pf2e/sync_srd.py --check
```

The first command looks up the Aid action. The second checks whether the local rules dataset needs synchronization without changing it. If those optional tools or data files are absent, use the campaign's licensed source material and record any table ruling.

### Table Rulings

Apply the four degrees of success every time a check has a DC. Announce the relevant action cost, MAP, reactions, and condition values before they become surprises. When a rule is uncertain, make a consistent temporary ruling, mark it for post-session lookup, and do not halt the encounter.
