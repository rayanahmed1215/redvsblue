// Vulnerability catalog. Nothing here is a real attack: each vulnerability is
// a rule that says "this component type is weak unless flag X is on".
//
// `fix` is the flag that actually stops it. `decoys` are fixes that sound
// plausible but don't work; the Defender has to learn the difference.

export const VULNS = [
  {
    id: 'sqli',
    name: 'SQL injection',
    technique: 'sqlInjection',
    techniqueLabel: 'Inject SQL',
    targets: ['loginForm', 'searchBox'],
    fix: 'paramQueries',
    decoys: ['inputValidation', 'rateLimit'],
    grants: 'dbAccess',
    severity: 'critical',
    explain: {
      what: 'The website builds a database command by gluing user input directly into it. An attacker types database code instead of normal text, and the database runs it.',
      example: "Typing  ' OR '1'='1  into a login box can turn the check \"is the password correct?\" into \"is 1 equal to 1?\", which is always true.",
      fix: 'Parameterized queries send the command and the user input separately. The database treats the input purely as data, never as part of the command.',
      decoyWhy: {
        inputValidation: 'Filtering characters helps, but attackers find ways around filters. Only separating data from code fully fixes it.',
        rateLimit: 'One injected request is enough, so slowing requests down does not stop it.',
      },
    },
  },
  {
    id: 'xss',
    name: 'Cross-site scripting (XSS)',
    technique: 'scriptInjection',
    techniqueLabel: 'Inject script',
    targets: ['commentSection', 'searchBox'],
    fix: 'outputEncoding',
    decoys: ['csrfToken', 'inputValidation'],
    severity: 'high',
    explain: {
      what: 'The site shows user-written text on a page without making it safe first. If that text contains a <script>, every visitor\'s browser runs it.',
      example: 'A comment like  <script>steal(document.cookie)</script>  could send every reader\'s login cookie to the attacker.',
      fix: 'Output encoding turns < into &lt; (and so on) before displaying text, so the browser shows the characters instead of running them.',
      decoyWhy: {
        csrfToken: 'CSRF tokens protect forms from being submitted by other sites. They do not change how stored text is displayed.',
        inputValidation: 'Blocking "<script>" is easy to bypass (there are hundreds of tricks). Encoding on output is the reliable fix.',
      },
    },
  },
  {
    id: 'idor',
    name: 'Broken access control (IDOR)',
    technique: 'idTampering',
    techniqueLabel: 'Tamper with ID',
    targets: ['profilePage', 'adminPanel'],
    fix: 'authCheck',
    decoys: ['inputValidation', 'csrfToken'],
    severity: 'high',
    explain: {
      what: 'The page decides what to show based only on a number in the URL. Change the number and you see someone else\'s data, or reach pages meant only for admins.',
      example: 'Changing  /profile?id=42  to  /profile?id=43  shows another user\'s private profile.',
      fix: 'An authorization check makes the server ask "is this logged-in user allowed to see record 43?" on every request.',
      decoyWhy: {
        inputValidation: '43 is a perfectly valid number. The input is fine; the missing piece is a permission check.',
        csrfToken: 'The attacker is just visiting a URL as themselves, not tricking another user, so CSRF tokens do not help.',
      },
    },
  },
  {
    id: 'bruteforce',
    name: 'Brute-force login',
    technique: 'passwordGuessing',
    techniqueLabel: 'Guess passwords',
    targets: ['loginForm', 'adminPanel'],
    fix: 'rateLimit',
    decoys: ['hashPasswords', 'inputValidation'],
    severity: 'medium',
    explain: {
      what: 'The login form lets anyone try as many passwords as they like, as fast as they like. A program can try thousands of common passwords per minute.',
      example: 'A script tries "password", "123456", "qwerty"... until one works for the admin account.',
      fix: 'Rate limiting (for example 5 attempts per minute, then a lockout) makes guessing take years instead of minutes.',
      decoyWhy: {
        hashPasswords: 'Hashing protects passwords if the database leaks, but the login form still answers every guess.',
        inputValidation: 'Every guess is a normal-looking password, so there is nothing to reject.',
      },
    },
  },
  {
    id: 'upload',
    name: 'Unrestricted file upload',
    technique: 'maliciousUpload',
    techniqueLabel: 'Upload script',
    targets: ['fileUpload'],
    fix: 'fileTypeCheck',
    decoys: ['inputValidation', 'outputEncoding'],
    severity: 'critical',
    explain: {
      what: 'The upload form accepts any file and stores it where the server will run it. An attacker uploads a program instead of a picture.',
      example: 'Uploading  avatar.php  (a tiny script) and then visiting  /uploads/avatar.php  gives the attacker control of the server.',
      fix: 'Check that files really are the expected type, rename them, and store them somewhere the server never executes code.',
      decoyWhy: {
        inputValidation: 'Checking the form fields does not inspect the file\'s contents.',
        outputEncoding: 'Encoding affects how text is displayed, not whether an uploaded file can run.',
      },
    },
  },
  {
    id: 'csrf',
    name: 'Cross-site request forgery (CSRF)',
    technique: 'forgedRequest',
    techniqueLabel: 'Forge request',
    targets: ['contactForm', 'commentSection', 'profilePage'],
    fix: 'csrfToken',
    decoys: ['authCheck', 'outputEncoding'],
    severity: 'medium',
    explain: {
      what: 'The site trusts any form submission that comes with your login cookie. A malicious page you visit can secretly submit a form to this site as you.',
      example: 'You open a funny cat page; hidden in it is a form that posts "change my email to attacker@evil.com" to your profile.',
      fix: 'A CSRF token is a secret random value placed in each real form. Forged forms from other sites cannot know it, so the server rejects them.',
      decoyWhy: {
        authCheck: 'The forged request really does come from the logged-in user\'s browser, so permission checks pass.',
        outputEncoding: 'No text is being displayed; the problem is who submitted the form.',
      },
    },
  },
  {
    id: 'pwleak',
    name: 'Plaintext password leak',
    technique: 'dumpPasswords',
    techniqueLabel: 'Dump passwords',
    targets: ['loginForm'],
    fix: 'hashPasswords',
    decoys: ['paramQueries', 'rateLimit'],
    requires: 'dbAccess',
    severity: 'critical',
    explain: {
      what: 'Passwords are stored exactly as users typed them. This only matters once an attacker reaches the database (for example via SQL injection), but then every password is exposed. This is attack chaining: one flaw opens the door to the next.',
      example: 'After an SQL injection, the attacker reads the users table and sees  alice : sunshine99.  Many people reuse passwords, so other sites are now at risk too.',
      fix: 'Hash passwords with a slow one-way function (bcrypt, argon2). Even with the database, the attacker only sees scrambled values.',
      decoyWhy: {
        paramQueries: 'This closes one way into the database, but the passwords are still readable if any other way in is found. Defense in depth means fixing both.',
        rateLimit: 'The attacker already has the data; slowing down logins does not hide it.',
      },
    },
  },
];

export const VULN_BY_ID = Object.fromEntries(VULNS.map((v) => [v.id, v]));
export const VULN_BY_TECHNIQUE = Object.fromEntries(VULNS.map((v) => [v.technique, v]));
export const TECHNIQUES = VULNS.map((v) => v.technique);

export function fixOptions(vuln) {
  return [vuln.fix, ...vuln.decoys];
}

// Is this component weak to this vulnerability right now? (Ignores any
// prerequisite like dbAccess; that is checked by the attacker.)
export function isVulnerable(vuln, comp) {
  return vuln.targets.includes(comp.type) && !comp.flags[vuln.fix];
}

export function vulnsForType(type) {
  return VULNS.filter((v) => v.targets.includes(type));
}

export function weaknesses(comp) {
  return vulnsForType(comp.type).filter((v) => isVulnerable(v, comp));
}

// Flags worth showing for a component type: every real fix and decoy that relates to it.
export function relevantFlags(type) {
  const set = new Set();
  for (const v of vulnsForType(type)) fixOptions(v).forEach((f) => set.add(f));
  return [...set];
}
