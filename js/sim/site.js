// The simulated website: a list of components, each with security "flags".
// Every flag starts false, because the Builder only cares about design.

export const FLAGS = {
  paramQueries: {
    label: 'Parameterized queries',
    desc: 'User input is sent to the database separately from the SQL command, so it can never be run as code.',
  },
  inputValidation: {
    label: 'Input validation',
    desc: 'Checks that input looks like what is expected (length, characters, format) before using it.',
  },
  outputEncoding: {
    label: 'Output encoding',
    desc: 'Turns characters like < and > into harmless text before showing user content on a page.',
  },
  csrfToken: {
    label: 'CSRF token',
    desc: 'A secret random value in every form, so other websites cannot submit forms on your behalf.',
  },
  authCheck: {
    label: 'Authorization check',
    desc: 'The server checks that the logged-in user is actually allowed to see or change this thing.',
  },
  rateLimit: {
    label: 'Rate limiting',
    desc: 'Limits how many attempts can be made per minute, which makes guessing passwords impractical.',
  },
  hashPasswords: {
    label: 'Password hashing',
    desc: 'Stores a one-way scrambled version of each password instead of the password itself.',
  },
  fileTypeCheck: {
    label: 'File type check',
    desc: 'Only accepts safe file types (like real images) and never lets uploaded files run as code.',
  },
};

export const COMPONENT_TYPES = {
  landingPage: { label: 'Landing page', path: '/' },
  contactForm: { label: 'Contact form', path: '/contact' },
  loginForm: { label: 'Login form', path: '/login' },
  searchBox: { label: 'Search box', path: '/search?q=' },
  commentSection: { label: 'Comments', path: '/posts/1/comments' },
  profilePage: { label: 'Profile page', path: '/profile?id=42' },
  fileUpload: { label: 'File upload', path: '/upload' },
  adminPanel: { label: 'Admin panel', path: '/admin', hidden: true },
};

export const STAGES = [
  { name: 'Landing page & contact', components: [['landingPage', 'Home page'], ['contactForm', 'Contact us']] },
  { name: 'User accounts', components: [['loginForm', 'Login']] },
  { name: 'Search & community', components: [['searchBox', 'Site search'], ['commentSection', 'Blog comments']] },
  { name: 'Profiles & avatars', components: [['profilePage', 'User profile'], ['fileUpload', 'Avatar upload']] },
  { name: 'Admin tools', components: [['adminPanel', 'Admin dashboard']] },
];

// Extra features the Builder keeps adding after the main stages are done.
export const FEATURE_NAMES = {
  contactForm: ['Newsletter signup', 'Support ticket form', 'Feedback form'],
  loginForm: ['Partner login', 'Mobile app login'],
  searchBox: ['Product search', 'Help center search', 'Store locator'],
  commentSection: ['Product reviews', 'Forum replies', 'Q&A board'],
  profilePage: ['Order history', 'Invoice viewer', 'Team page'],
  fileUpload: ['Document upload', 'Resume upload'],
  adminPanel: ['Staff tools', 'Debug console'],
};

export const MAX_COMPONENTS = 16;

export function createSite() {
  return { components: [], nextId: 1 };
}

export function makeFlags() {
  return Object.fromEntries(Object.keys(FLAGS).map((f) => [f, false]));
}

export function addComponent(site, type, name, stage, round = 0) {
  const def = COMPONENT_TYPES[type];
  if (!def) throw new Error(`Unknown component type: ${type}`);
  const comp = {
    id: `c${site.nextId++}`,
    type,
    name,
    path: def.path,
    stage,
    hidden: Boolean(def.hidden),
    flags: makeFlags(),
    open: new Set(), // vuln ids that were breached and are not yet verified fixed
    lastBreachRound: -1,
    createdRound: round,
    history: [],
  };
  site.components.push(comp);
  return comp;
}

export function getComponent(site, id) {
  return site.components.find((c) => c.id === id);
}
