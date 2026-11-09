# RvB Learning Lab

A simulated red team vs blue team system that runs itself, so you can learn web security by watching it.

- **Builder** builds a pretend website in stages and only thinks about features.
- **Attacker (red)** learns by trial and error which attacks break which pages. It gets +10 for a breach and −0.5 for a failed try.
- **Defender (blue)** gets each breach report and has to *learn* which fix actually works. Some fixes sound right but don't. The Attacker retests every fix. Fixes that keep working become **secure coding rules** that the Builder follows on new pages.

Nothing here is real hacking. Each weakness is a simple rule like "a search box is open to SQL injection unless parameterized queries are on."

## Run it

```bash
python3 -m http.server 8000     # or: npm start
```

Open http://localhost:8000 and press **Play**. Click any attack name to learn what it is and how it's fixed, or click a page on the site map to see its security settings.

## Tests

```bash
npm test
```

The tests check that the vulnerability rules are consistent, that each agent learns, and that across several seeds the attacker's breaches go down while the defender's fix accuracy goes up.

## Attacks in the simulation

| Attack | Hits | Real fix |
|---|---|---|
| SQL injection | Login, search | Parameterized queries |
| Cross-site scripting (XSS) | Comments, search | Output encoding |
| Broken access control (IDOR) | Profile pages, admin | Authorization check |
| Brute-force login | Login, admin | Rate limiting |
| Unrestricted file upload | File upload | File type check |
| CSRF | Forms, comments, profiles | CSRF token |
| Plaintext password leak | Login (only after SQL injection) | Password hashing |

## Code layout

```
js/sim/       vulns.js (catalog + explanations), site.js (pages & flags), engine.js (round loop), rng.js, events.js
js/agents/    attacker.js (Q-learning), defender.js (fix learning + rules), builder.js
js/ui/        site map, agent panels, charts, event log, explanation popups
test/         node --test suites
```

## Ideas to extend

- Add a new vulnerability: add an entry to `js/sim/vulns.js`, with its target page types, its real fix, decoy fixes and an explanation.
- Give the Defender a monitoring budget so it can detect attacks *while they happen*, not only after a breach.
- Let the Attacker learn multi-step chains with full Q-learning (next-state values).
