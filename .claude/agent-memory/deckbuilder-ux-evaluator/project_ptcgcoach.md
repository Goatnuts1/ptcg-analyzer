---
name: project-ptcgcoach
description: What PTCGCoach is, where it lives, and how to drive/evaluate it
metadata:
  type: project
---

PTCGCoach is a native SwiftUI iPhone app for Pokémon TCG deck building/analysis at `/Users/chrisai/dev/PTCGCoach`. 3 tabs: Meta (ranked meta decks + matchup board), Decks (import TCG-Live list, legality check, on-device Monte Carlo prize-race sim + strategy), Review (import battle log, turn-by-turn + Coach Analysis path-to-victory).

**Why:** We dogfood it as both an end-user deck optimizer and an App-Store reviewer.

**How to apply:**
- Build (slow; a heavy ML job pins CPU): `export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` then `xcodebuild -project PTCGCoach.xcodeproj -scheme PTCGCoach -destination 'platform=iOS Simulator,name=iPhone 17' -derivedDataPath build build`. simctl ALSO needs DEVELOPER_DIR exported or it errors "unable to find utility simctl".
- simctl can't tap/type. Drive screens via `SIMCTL_CHILD_PTCG_*` env hooks: `PTCG_TAB=0|1|2`, `PTCG_AUTOSIM=1` (Gardevoir sim), `PTCG_SIM_SCROLL=changes|plays`, `PTCG_SIM_EXPAND=1`, `PTCG_AUTOREVIEW=1`, `PTCG_AUTOANALYZE=1`, `PTCG_SEEDGAME=1`. Screenshot: `xcrun simctl io "iPhone 17" screenshot /tmp/x.png` then Read it.
- Fast native logic harness (NO Xcode): entry file MUST be literally named `main.swift`; `swiftc -O -o /tmp/x PTCGCoach/Models/*.swift /tmp/sw/main.swift`. Bundled data: `PTCGCoach/Resources/{cards.json (1284 cards), meta_decks.json (13 decks)}`. Models are Foundation-only.
- Card fields that drive the sim live in cards.json: hp, maxDamage, dmgSuffix (×/+ = scaling), attackCost, weakness, stage (0/1/2), isEx, prizeValue, types, mark (H/I/J legal).
