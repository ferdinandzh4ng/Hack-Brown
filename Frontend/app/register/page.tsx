'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { LogIn, Sparkles } from 'lucide-react';
import { registerWithEmail } from '@/lib/auth';

export default function RegisterPage() {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim()) {
      setError('Please enter your email.');
      return;
    }
    if (!username.trim()) {
      setError('Please choose a username (at least 3 characters).');
      return;
    }
    if (username.trim().length < 3) {
      setError('Username must be at least 3 characters.');
      return;
    }
    if (!password || password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }
    setLoading(true);
    try {
      const data = await registerWithEmail(
        email.trim(),
        username.trim(),
        password,
        fullName.trim() || undefined
      );
      if (data?.token) {
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('session_token', data.token);
        }
        // Redirect to onboarding if required, otherwise to home
        if (data?.onboarding_required) {
          window.location.href = '/onboarding';
        } else {
          window.location.href = '/';
        }
        return;
      }
      if (data?.success) {
        setSuccess(true);
        return;
      }
      setError(data?.message ?? 'Registration failed. Please try again.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-bg safe-area-padding px-4 py-12">
        <div className="max-w-md w-full bg-white rounded-3xl shadow-visa-card p-8 border border-slate-border text-center">
          <p className="text-slate-muted mb-4">Account created. Redirecting to sign in…</p>
          <Link href="/login" className="text-visa-blue font-semibold inline-flex items-center gap-2 hover:underline">
            <LogIn className="w-4 h-4" /> Go to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-bg safe-area-padding px-4 py-12">
      <div className="max-w-md w-full bg-white rounded-3xl shadow-visa-card p-8 border border-slate-border">
        <div className="flex flex-col items-center gap-3 mb-6">
          <div className="p-2.5 rounded-xl bg-visa-blue">
            <Sparkles className="w-6 h-6 text-white" />
          </div>
          <h1 className="font-heading text-2xl font-bold text-visa-blue">
            Create an account
          </h1>
          <p className="text-sm text-slate-muted text-center">
            Join Hack-Brown to plan trips and get personalized recommendations.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="reg-email" className="block text-xs font-semibold text-slate-900 mb-2">
              Email
            </label>
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="font-sans w-full bg-slate-trust-100 border border-slate-border text-slate-900 p-3 md:p-4 rounded-xl text-sm md:text-base placeholder:text-slate-muted focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
            />
          </div>
          <div>
            <label htmlFor="reg-username" className="block text-xs font-semibold text-slate-900 mb-2">
              Username
            </label>
            <input
              id="reg-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="johndoe"
              className="font-sans w-full bg-slate-trust-100 border border-slate-border text-slate-900 p-3 md:p-4 rounded-xl text-sm md:text-base placeholder:text-slate-muted focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
            />
          </div>
          <div>
            <label htmlFor="reg-fullname" className="block text-xs font-semibold text-slate-900 mb-2">
              Full name <span className="text-slate-muted font-normal">(optional)</span>
            </label>
            <input
              id="reg-fullname"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="John Doe"
              className="font-sans w-full bg-slate-trust-100 border border-slate-border text-slate-900 p-3 md:p-4 rounded-xl text-sm md:text-base placeholder:text-slate-muted focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
            />
          </div>
          <div>
            <label htmlFor="reg-password" className="block text-xs font-semibold text-slate-900 mb-2">
              Password
            </label>
            <input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              className="font-sans w-full bg-slate-trust-100 border border-slate-border text-slate-900 p-3 md:p-4 rounded-xl text-sm md:text-base placeholder:text-slate-muted focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
            />
          </div>
          {error && (
            <div className="p-3 rounded-xl text-sm bg-red-50 text-red-700 border border-red-100">
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            className="font-heading w-full py-3 md:py-4 rounded-xl font-bold text-sm md:text-base bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-sm text-slate-muted mt-6">
          Already have an account?{' '}
          <Link href="/login" className="text-visa-blue font-semibold inline-flex items-center gap-2 hover:underline">
            <LogIn className="w-4 h-4" /> Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
