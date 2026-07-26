# System Module — Cairn 2e

Source: [Cairn 2e SRD](https://cairnrpg.com/second-edition/#second-edition) (CC-BY-SA 4.0)

---

## Dice Convention

**Core resolution:** Roll 1d20 and compare to the relevant attribute (STR, DEX, or WIL). Roll **equal to or under** the attribute to succeed. Roll **above** the attribute to fail. **Matching the attribute is a success.**

**Special results:** 1 is **always** a success. 20 is **always** a failure, regardless of attribute values.

**Combat resolution:** Attacks in combat **automatically hit** — no attack roll. The attacker rolls their weapon die for damage, subtracts the target's Armor, and deals the remainder to HP.

**Multiple attackers on one target:** Roll all damage dice separately, then keep only the **single highest** result.

**No advantage/disadvantage system.** Difficulty is adjudicated by the Warden through context, not modifiers.

**Opposed situations:** When two opponents try to overcome each other, the one **most at risk** saves.

**Aiding an ally:** When two characters act together on something risky, the one **most at risk** (usually lowest relevant attribute) saves.

**Die of Fate:** Optionally roll 1d6 when outcomes are uncertain. 4+ favors the PCs. 3 or under means bad luck for the PCs.

**Example inline combat narration:**
`[Character] attacks [target]: weapon die = [roll] → [result] minus [Armor] = [damage] to HP`

---

## Ability Scores / Statistics

Three attributes, no derived modifiers — the attribute **is** the save target.

| Stat | Governs |
|------|---------|
| **STR** | Physical power, lifting, bending, resisting poison, endurance |
| **DEX** | Poise, speed, reflexes, dodging, climbing, sneaking, balancing |
| **WIL** | Persuasion, deception, interrogation, intimidation, charm, spell manipulation |

Attributes are **not universal descriptors.** A low STR does not mean a character is hopelessly weak — they can still attempt heavy feats, just at higher risk.

---

## Character Creation

1. **Background:** Roll or choose from 20 backgrounds (d20). Each background provides starting equipment, skills, and abilities.
2. **Name:** Choose from the available list for the rolled background.
3. **Attributes:** Roll 3d6 for STR, DEX, and WIL in order. You may then **swap any two** results.
4. **Hit Protection (HP):** Roll 1d6. This reflects combat skill, luck, and resilience — not fortitude. It refreshes quickly when safe.
5. **Inventory:** 10 total slots. Comfortable carry: 4–5 items without bags/backpacks/horses. Each PC starts with a **Backpack** (holds 6 slots). A full inventory (10 slots) reduces HP to 0.
6. **Items:** Most items take 1 slot. *Petty* items take 0 slots. *Bulky* items take 2 slots. Bags of coins under 100gp are petty.
7. **Traits:** Roll d10 for Physique, Skin, Hair, Face, Speech, Clothing, Virtue, and Vice.
8. **Bonds:** Roll d20 for a starting bond (background story hook).
9. **Age:** Roll 2d20+10. The youngest character rolls on the Omens table.

### Backgrounds (d20)

| Roll | Background | Roll | Background |
|------|-----------|------|-----------|
| 1 | Aurifex | 11 | Half-Witch |
| 2 | Barber-Surgeon | 12 | Hexenbane |
| 3 | Beast Handler | 13 | Jongleur |
| 4 | Bonekeeper | 14 | Kettlewright |
| 5 | Cutpurse | 15 | Marchguard |
| 6 | Fieldwarden | 16 | Mountebank |
| 7 | Fletchwind | 17 | Outrider |
| 8 | Foundling | 18 | Prowler |
| 9 | Fungal Forager | 19 | Rill Runner |
| 10 | Greenwise | 20 | Scrivener |

**What each background provides:** Names list, starting gear (weapon, armor, adventuring gear, gold via 3d6), and two 1d6 random tables for unique traits or items. Proficiency with starting weapons is implied fiction-first — if you carry it, you know how to use it.

**Background examples (gear summary):**
- **Aurifex** — Needle-knife (d6), Protective Gloves, Lantern, Oil Can. Unique: alchemical mishap table + alchemical marvel table.
- **Cutpurse** — Twin Daggers (d6+d6, bulky), Padded Leather (1 Armor), Lockpicks. Unique: last-big-job table + magical tool table.
- **Foundling** — Sling (d6), Dagger (d6), Heirloom Amulet (glows near magic). Unique: caretaker table + keepsake table. Rolls on Omens table regardless of age.
- **Half-Witch** — Iron Dagger (d6), Spellbook, Herbs Pouch, Ghillie Suit. Unique: Unseelie Court table + concoction table.
- **Marchguard** — Heavy armor (likely 2 Armor), shield, martial weapon. The tanky martial background.

Each background has its own full page with names, gear, and two detailed random tables. Consult https://cairnrpg.com/second-edition/backgrounds/ when creating a character.

---

## Health and Damage

**HP (Hit Protection):** Reflects combat skill, stamina, and luck. Refreshes quickly when safe and comfortable. Not a measure of physical toughness.

**Combat damage:** Weapon die → subtract Armor → remainder reduces HP.

**Attack modifiers:**
- **Impaired** (weakness position, cover, bound hands): roll 1d4 damage regardless of weapon. Unarmed attacks always do d4.
- **Enhanced** (advantage position, helpless foe, daring maneuver): roll 1d12 instead of normal weapon die.
- **Two-weapon attack:** Roll both damage dice, keep the single highest.
- **Blast quality:** Affects all targets in noted area, rolling separately for each.
- **Ranged attacks:** Can target any enemy in sight. Especially distant targets are Impaired. Ammunition is not tracked unless specified.

**Armor:** Subtract from damage before reducing HP. Shields provide +1 Armor while held/worn. Max Armor is 3.

**Critical Damage:** When damage reduces HP **below zero**, the excess is subtracted from STR. The target must then immediately make a **STR save** using their **new (reduced) STR score.**
- **Success:** Still in the fight with reduced STR. Continue making critical damage saves when taking more damage.
- **Failure:** Defeated. NPCs and monsters die. PCs cannot do anything but crawl weakly — if given aid (bandages), they stabilize. If untreated, they die within the hour.

**Attribute Loss (outside combat or defenseless targets):** When an opponent is defenseless, blinded, or otherwise unable to defend themselves, damage bypasses HP and goes directly to an attribute (usually STR). Damage from traps also goes to attributes, not HP.
- STR reduced to 0: **die**
- DEX reduced to 0: **paralyzed**
- WIL reduced to 0: **delirious** (unable to act until restored)

**Scars:** When damage reduces a PC's HP to **exactly 0**, roll on the Scars table based on how much HP was lost in the attack (1 = Lasting Scar, 2 = Rattling Blow, ... up to 12 = Doomed). Scars can yield both positive and negative consequences. Repeat chain results if the table entry's roll exceeds max HP.

**Character Death:** Player creates a new character or takes control of a hireling. They join the party immediately.

---

## Primary Resource

**Hit Protection (HP)** is the primary combat resource — it absorbs damage and refreshes when safe.

**Inventory slots** are the primary exploration resource — limited to 10, and a full load means HP drops to 0.

**Fatigue** occupies inventory slots. Each Fatigue costs 1 slot and lasts until the PC recuperates (e.g., full night's rest in a safe spot). If forced to add Fatigue with no free slots, drop an item.

**No spell slots, mana, or similar.** Magic uses Fatigue (see Magic section).

---

## Rests and Recovery

**In dungeons:** A character can spend a turn **resting** to restore all HP. Requires a light source and safe location. Resting does **not** restore Fatigue (cannot Make Camp in a dungeon).

**In the wilderness:** **Make Camp** action — each party member consumes 1 Ration. Party members that rest remove **all Fatigue** from their inventory. A lookout rotation is required.

**Deprivation:** A PC lacking a crucial need (food, rest) is **Deprived.** Anyone Deprived for more than a day adds Fatigue (one per day). A Deprived PC cannot recover HP, Attributes, or item slots from Fatigue.

**Attribute loss recovery:** Usually restored with a week's rest, facilitated by a healer or expertise.

**Healing services:** Some are free; magical or expedient means may cost gold.

Map to `calendar.py`:
- `calendar.py rest short` → +1 hour
- `calendar.py rest long` → +8 hours (wilderness Make Camp)

---

## Incapacitation and Death

**At 0 HP (exactly):** Roll on the **Scars table** (see above). The specific scar depends on HP lost in the final hit.

**Below 0 HP (Critical Damage):** Excess damage reduces STR. STR save or be defeated:
- **PC:** Crawl weakly, stabilize with aid or die within the hour.
- **NPC/Monster:** Dead.

**Attribute at 0:** STR = death, DEX = paralysis, WIL = delirious. Complete DEX and WIL loss = unable to act until restored.

**Panicked:** A panicked character has 0 HP, does not act in the first round of combat, and all attacks are Impaired. Make a WIL save as an action to overcome.

**No death saves in the D&D sense.** The critical damage STR save is the death mechanic.

---

## Status Effects / Conditions

| Condition | Severity | Effect summary |
|-----------|----------|----------------|
| Deprived | danger | Cannot recover HP, attributes, or slots from Fatigue. Adds Fatigue each day. |
| Fatigue | warn | Occupies 1 inventory slot each. Removed by safe rest (Make Camp). |
| Panicked | danger | 0 HP, no first-round action, all attacks Impaired. WIL save to overcome. |
| Impaired | warn | Roll 1d4 damage regardless of weapon die. Applies from disadvantaged position. |
| Enhanced | buff | Roll 1d12 damage instead of weapon die. Applies from advantaged position. |

---

## Advancement (Growth)

Cairn 2e uses **fiction-first Growth** — no XP, no levels. Characters change through meaningful in-game experiences, not mechanical thresholds.

**Growth Triggers** — a character grows when they engage with the game world in at least two of these ways:
- **Focused behavior** — a consistent pattern of action around a single objective.
- **Taking risks** — obvious risk with serious consequences, especially when the outcome is unknown.
- **Interacting with the unknown** — a unique item, creature, entity, or power not fully understood.

**Growth is not a reward** — it is the logical result of a character's actions. The Warden grants Growth when triggers are met, and the change should be tied to the specific fiction (not arbitrary).

**Growth Examples:**
- Learning to cast a spell without a WIL save after repeated successful casting under duress.
- Gaining a physical mutation after ingesting a magical substance.
- Earning a faction rank after completing missions.
- Losing an old fear after overcoming a long-time foe.

**Downtime** (between sessions): Research, Training, Strengthening Ties. These provide structured triggers for Growth but are not the only path — Growth happens during play as often as during Downtime.

---

## Bold Play Reward

**Reward name:** Inspiration (fiction-based, not a formal mechanic)
**Effect:** The Warden should reward bold play narratively — unexpected choices that work should work *better* than the expected one.
**How to award:** Immediate narrative reward when a player takes a creative risk, commits hard to a roleplay choice, or does something surprising that makes the scene better.

---

## Campaign Arc Preferences

**Preferred campaign mode:** Either (improvised dynamic arc recommended for Cairn's sandbox feel).
**Typical arc structure:** Dynamic (improvised from threat, factions, and Three Truths) or sandbox. Hub-and-spoke suits wilderness exploration and hexcrawl.
**Genre conventions:** Cairn is fiction-first, danger-forward, and classless. Emphasize exploration, discovery, and consequence over combat optimization. Combat is fast, hectic, and lethal — telegraph danger before it kills. Retreat always requires a DEX save plus a safe destination.

---

## Combat (Detailed)

### Rounds
A Round is roughly 10 seconds. Each side (PCs vs opponents) acts together. Results of a side's actions occur **simultaneously.**

**First round:** Each PC must make a **DEX save** to act. Fail = lose your turn for the first round only. Then opponents act. Round 1 ends. From round 2 onward, PCs act first, then opponents.

### Actions
On their turn, a character may **move up to 40ft** and take **one action** (attack, cast a spell, move again, or another reasonable action). All actions are declared before dice are rolled.

### Retreating
Running away always requires a successful **DEX save** plus a safe destination to run to.

### Morale
Enemies must pass a **WIL save** to avoid fleeing when they take their first casualty, and again when they lose half their number. Lone foes save at 0 HP. Morale does not affect PCs. Groups may use their leader's WIL.

### Reactions
When NPC reaction is unknown, roll 2d6:
| 2 | 3–5 | 6–8 | 9–11 | 12 |
|---|-----|-----|------|----|
| Hostile | Wary | Curious | Kind | Helpful |

### Detachments
Large groups of similar combatants fighting as one. Critical Damage routes or weakens them. At 0 STR, destroyed. Attacks against detachments by individuals are Impaired (except Blast). Attacks against individuals by detachments are Enhanced and deal Blast damage.

---

## Magic

### Spellbooks
Contain a single spell, take 1 slot. Cannot be easily transcribed — found in tombs, dungeons, manors. May display unusual properties. Attract dangerous attention.

### Casting
Anyone can cast by holding a Spellbook with both hands and reading aloud. Must add **1 Fatigue** to inventory. Given time and safety, can enhance impact (multiple targets, increased power) at no extra cost. If Deprived or in danger, Warden may require a **WIL save** to avoid ill effects (added Fatigue, destroyed Spellbook, injury, or death).

### Scrolls
Like Spellbooks but: Petty, no Fatigue cost, disappear after one use.

### Relics
Items imbued with magical power. No Fatigue cost. Usually limited use with a Recharge condition. When first acquired and unfamiliar, a PC can either spend Downtime learning about it, or experiment with it — the latter carries dangers and may require a **WIL save** to avoid negative consequences. The Warden may simply tell the player how it works when appropriate.

---

## Inventory System

**Slots:** 10 total per character. Most items = 1 slot. Petty = 0. Bulky = 2.

**Comfortable carry:** 4–5 items without bags. A Backpack holds up to 6 slots.

**Full inventory (10 slots) = 0 HP.** Cannot exceed 10 slots.

**Fatigue** occupies slots. Forced to add Fatigue with no slots = drop an item.

---

## Hirelings

Recruitable NPCs with unique skills. Create by choosing a role, rolling 3d6 for each attribute, 1d6 for HP. Give appropriate equipment. Roll on Character Traits tables. Alternatively, choose a background and name, then roll for equipment, gold, attributes, HP, and age.

---

## Warden Principles (Cairn-Specific)

- **Fiction-first:** Success and failure are based on in-world elements, not dice.
- **Information freely given:** Maximal sensory details about the environment. No Perception rolls.
- **No knowledge mechanics:** Characters know things if it can be justified in the fiction. Use Die of Fate for uncertain knowledge.
- **Danger is real but never random:** Telegraph serious danger. Traps in plain sight. Death never a surprise.
- **Player choice:** Give players solid choices. Binary "A or B?" when intentions are vague.
- **NPCs have self-interest:** They don't want to die. They remember what PCs say and do.
