const STORAGE_KEY = 'mmr_admin_session_token'

export function getSessionToken(): string | null {
  // api.ts calls this on every request, public ones included, so blocked
  // storage must not stop a public signup from going through
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setSessionToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token)
}

export function clearSessionToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}
