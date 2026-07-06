import type { AxiosError } from 'axios';

/** True when the API is temporarily unreachable (not an auth rejection). */
export function isTransientApiError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const ax = error as AxiosError;
  if (!ax.isAxiosError) return false;
  if (!ax.response) return true;
  const status = ax.response.status;
  return status === 502 || status === 503 || status === 504 || status === 408;
}

export function isAuthError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const ax = error as AxiosError;
  return ax.isAxiosError === true && ax.response?.status === 401;
}
