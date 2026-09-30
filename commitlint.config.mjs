// Conventional Commits, enforced locally (pre-commit commit-msg hook) and in CI (commits + PR title).
// Format: <type>(<scope>): <subject>   e.g. feat(requests): enforce status transitions
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'header-max-length': [2, 'always', 72],
    'subject-case': [2, 'never', ['sentence-case', 'start-case', 'pascal-case', 'upper-case']],
    'scope-enum': [
      2,
      'always',
      [
        'auth',
        'users',
        'requests',
        'episodes',
        'import',
        'assignments',
        'analytics',
        'api',
        'core',
        'db',
        'ui',
        'backend',
        'frontend',
        'docker',
        'ci',
        'cd',
        'deps',
        'deps-dev',
        'release',
      ],
    ],
  },
  // Dependabot uses its own message format (capitalised subject, long body lines).
  ignores: [(message) => message.includes('dependabot[bot]')],
};
