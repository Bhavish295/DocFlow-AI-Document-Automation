export const Permission = {
  DOCUMENTS_READ: 'documents:read',
  DOCUMENTS_WRITE: 'documents:write',
  DOCUMENTS_PROCESS: 'documents:process',
  DOCUMENTS_EXTRACT: 'documents:extract',
  DOCUMENTS_INDEX: 'documents:index',
  PROCESSING_JOBS_WRITE: 'processing_jobs:write',
  VALIDATIONS_WRITE: 'validations:write',
  RELATIONSHIPS_WRITE: 'relationships:write',
  REVIEWS_WRITE: 'reviews:write',
  DUPLICATES_CHECK: 'duplicates:check',
  DUPLICATES_RESOLVE: 'duplicates:resolve',
  VENDORS_WRITE: 'vendors:write',
  ANOMALIES_SCORE: 'anomalies:score',
  ANOMALIES_TRAIN: 'anomalies:train',
  CLASSIFICATION_TRAIN: 'classification:train',
  WORKFLOWS_TRIGGER: 'workflows:trigger',
  ANALYTICS_READ: 'analytics:read',
  USERS_MANAGE: 'users:manage',
}

const VIEWER = new Set([
  Permission.DOCUMENTS_READ,
  Permission.ANALYTICS_READ,
])

const OPERATOR = new Set([
  ...VIEWER,
  Permission.DOCUMENTS_WRITE,
  Permission.DOCUMENTS_PROCESS,
  Permission.DOCUMENTS_EXTRACT,
  Permission.DOCUMENTS_INDEX,
  Permission.PROCESSING_JOBS_WRITE,
  Permission.VALIDATIONS_WRITE,
  Permission.RELATIONSHIPS_WRITE,
  Permission.DUPLICATES_CHECK,
  Permission.VENDORS_WRITE,
  Permission.ANOMALIES_SCORE,
  Permission.WORKFLOWS_TRIGGER,
])

const REVIEWER = new Set([
  ...VIEWER,
  Permission.REVIEWS_WRITE,
  Permission.DUPLICATES_RESOLVE,
  Permission.VALIDATIONS_WRITE,
])

const ADMIN = new Set(Object.values(Permission))

const ROLE_PERMISSIONS = {
  viewer: VIEWER,
  operator: OPERATOR,
  reviewer: REVIEWER,
  admin: ADMIN,
}

export function roleHasPermission(role, permission) {
  if (!role || !permission) return false
  if (role === 'admin') return true
  const set = ROLE_PERMISSIONS[role]
  return Boolean(set && set.has(permission))
}
