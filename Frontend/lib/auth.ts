/**
 * Auth helpers for Hack-Brown frontend.
 * Backend: set NEXT_PUBLIC_AUTH_API_URL (e.g. http://localhost:8000) if you have an auth API.
 */

const AUTH_API_URL = process.env.NEXT_PUBLIC_AUTH_API_URL ?? '';

export interface AuthResponse {
  token?: string;
  success?: boolean;
  message?: string;
}

/** Sign in with Google ID token; returns session token from backend or undefined. */
export async function googleSignIn(idToken: string): Promise<AuthResponse> {
  if (!AUTH_API_URL) {
    // Dev fallback: no backend – return a mock token so UI flow works
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
      return { token: `dev-google-${idToken.slice(0, 12)}`, success: true };
    }
    console.warn('NEXT_PUBLIC_AUTH_API_URL not set; Google sign-in will not call backend.');
    return { success: false, message: 'Auth API not configured' };
  }

  try {
    const res = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/google`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: idToken }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, message: data?.message ?? res.statusText };
    }
    return { token: data?.token ?? data?.session_token, success: true, ...data };
  } catch (err) {
    console.error('Google sign-in request failed', err);
    return { success: false, message: err instanceof Error ? err.message : 'Network error' };
  }
}

/** Register with email, username, password; returns success message or error. */
export async function registerWithEmail(
  email: string,
  username: string,
  password: string,
  fullName?: string
): Promise<AuthResponse & { token?: string }> {
  if (!AUTH_API_URL) {
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development' && email && username && password) {
      return { token: `dev-email-${btoa(email).slice(0, 12)}`, success: true };
    }
    return { success: false, message: 'Auth API not configured' };
  }
  try {
    const res = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, username, password, full_name: fullName }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return { success: false, message: data?.message ?? res.statusText };
    return { token: data?.token ?? data?.session_token, success: true, ...data };
  } catch (err) {
    console.error('Register request failed', err);
    return { success: false, message: err instanceof Error ? err.message : 'Network error' };
  }
}

/** Sign in with email and password; returns session token. */
export async function signInWithEmail(
  email: string,
  password: string
): Promise<AuthResponse> {
  if (!AUTH_API_URL) {
    if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
      // Dev fallback: accept any non-empty password
      if (email && password) {
        return { token: `dev-email-${btoa(email).slice(0, 12)}`, success: true };
      }
    }
    return { success: false, message: 'Auth API not configured' };
  }

  try {
    const res = await fetch(`${AUTH_API_URL.replace(/\/$/, '')}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, message: data?.message ?? res.statusText };
    }
    return { token: data?.token ?? data?.session_token, success: true, ...data };
  } catch (err) {
    console.error('Email sign-in request failed', err);
    return { success: false, message: err instanceof Error ? err.message : 'Network error' };
  }
}
