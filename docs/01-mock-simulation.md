# 1. The mock simulation (first draft)

**Date:** Nov 8. **Code:** `index.html`, `js/`, `css/`, `test/`. **Run:** `npm start`, then open http://localhost:8000.

## The idea
A red team vs blue team game that runs itself in the browser:

- **Builder** adds pages to a pretend website in stages and only thinks about features.
- **Red (attacker)** learns by trial and error which attacks break which pages. It scores **+10 for a breach** and **−0.5 for a failed try**.
- **Blue (defender)** gets each breach report and has to learn which fix works. Some fixes sound right but don't (these are called **decoy fixes**). Red retests every fix. A fix that works twice in a row becomes a **secure-coding rule**, and the Builder follows it on new pages.

## The 7 attacks it models

| Attack | What it hits | Real fix |
|---|---|---|
| SQL injection | Login, search | Parameterized queries |
| Cross-site scripting (XSS) | Comments, search | Output encoding |
| Broken access control (IDOR) | Profile pages, admin | Authorization check |
| Brute-force login | Login, admin | Rate limiting |
| Unrestricted file upload | File upload | File type check |
| CSRF | Forms, comments, profiles | CSRF token |
| Plaintext password leak | Login (only after SQL injection) | Password hashing |

Short definitions:
- **SQL injection:** typing database commands into a form so the site runs them.
- **XSS:** getting your own script to run in other people's browsers.
- **IDOR:** changing an ID in the URL to see someone else's data.
- **CSRF:** tricking a logged-in user's browser into submitting a form they didn't mean to.

## What each agent actually learned
- **Red:** a table of about 60 numbers, one for each (attack, page type) pair. After each try, the number moves 30% of the way toward the result. How often it explores at random starts at 100% and drops to 5%. This is a simple form of **Q-learning** (learning a score for each choice from rewards).
- **Blue:** 3 possible fixes per attack, each with a score. A fix that passes the retest is pulled toward +5, and one that fails toward −2. Two passes in a row locks the fix in as a rule.
- **Builder:** learns nothing. It follows Blue's rules, but "forgets" one 15% of the time.

## Test result: Blue hits a ceiling
6 seeds × 2,000 rounds each:

| Measure | Result |
|---|---|
| Rules learned | 6 or 7 of 7. The password rule is sometimes never learned, because SQL injection gets fixed first. |
| Last new rule learned | Between round 121 and round 1,482 |
| Fix accuracy after that | 100% |
| Breaches after that | About 1–2 per 100 rounds, all caused by the Builder forgetting a rule |

## Why we moved on
Looking at the code showed the whole thing was fake:
- A "page" is a JavaScript object with 8 true/false security switches. There's no HTML, no server and no database.
- An "attack" just checks whether the right switch is off, then flips a 90% coin.
- A "fix" is one line: `page.flags[flag] = true`.

The attack list is fixed and every attack has exactly one right fix, so Blue always reaches 100% and the game is solved. Nothing is learned that applies to real code.

**Decision:** "start with just designing a website, forget about red and blue for now." Build a **real** website first, written by an AI Builder, so that Red and Blue will later have real code to attack and fix. The simulation stays in the repo as a reference.
