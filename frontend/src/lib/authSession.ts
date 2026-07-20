const TOKEN_KEY = 'cv_token';

const REFRESH_KEY = 'cv_refresh_token';

const EXPIRES_KEY = 'cv_token_expires_at';

const ORG_KEY = 'cv_org_id';

const PERSIST_KEY = 'cv-auth';



export function getAuthCredentials(): { token: string | null; orgId: string | null } {

  return {

    token: localStorage.getItem(TOKEN_KEY),

    orgId: localStorage.getItem(ORG_KEY),

  };

}



export function getRefreshToken(): string | null {

  return localStorage.getItem(REFRESH_KEY);

}



export function getTokenExpiresAt(): number | null {

  const raw = localStorage.getItem(EXPIRES_KEY);

  return raw ? Number(raw) : null;

}



export function syncAuthSession(

  token: string | null,

  orgId: string | null,

  refreshToken?: string | null,

  expiresInSec?: number,

) {

  if (token) {

    localStorage.setItem(TOKEN_KEY, token);

  } else {

    localStorage.removeItem(TOKEN_KEY);

  }

  if (orgId) {

    localStorage.setItem(ORG_KEY, orgId);

  } else {

    localStorage.removeItem(ORG_KEY);

  }

  if (refreshToken !== undefined) {

    if (refreshToken) {

      localStorage.setItem(REFRESH_KEY, refreshToken);

    } else {

      localStorage.removeItem(REFRESH_KEY);

    }

  }

  if (expiresInSec !== undefined && token) {

    const expiresAt = Date.now() + expiresInSec * 1000;

    localStorage.setItem(EXPIRES_KEY, String(expiresAt));

  }

}



export function clearAuthSession() {

  localStorage.removeItem(TOKEN_KEY);

  localStorage.removeItem(REFRESH_KEY);

  localStorage.removeItem(EXPIRES_KEY);

  localStorage.removeItem(ORG_KEY);

  localStorage.removeItem(PERSIST_KEY);

}



export function isTokenExpiringSoon(thresholdMs = 60_000): boolean {

  const expiresAt = getTokenExpiresAt();

  if (!expiresAt) return false;

  return Date.now() >= expiresAt - thresholdMs;

}

