'use client';

import React, { useState } from 'react';
import { signInWithEmail } from '@/lib/auth';

interface LoginFormProps {
  onSuccess: (token: string) => void;
}

export default function LoginForm({ onSuccess }: LoginFormProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim()) {
      setError('Please enter your email.');
      return;
    }
    if (!password) {
      setError('Please enter your password.');
      return;
    }
    setLoading(true);
    try {
      const data = await signInWithEmail(email.trim(), password);
      if (data?.token) {
        onSuccess(data.token);
        return;
      }
      setError(data?.message ?? 'Sign-in failed. Please try again.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="login-email" className="block text-xs font-semibold text-slate-900 mb-2">
          Email
        </label>
        <input
          id="login-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="font-sans w-full bg-slate-trust-100 border border-slate-border text-slate-900 p-3 md:p-4 rounded-xl text-sm md:text-base placeholder:text-slate-muted focus:outline-none focus:ring-2 focus:ring-visa-blue/20"
        />
      </div>
      <div>
        <label htmlFor="login-password" className="block text-xs font-semibold text-slate-900 mb-2">
          Password
        </label>
        <input
          id="login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
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
        {loading ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}
