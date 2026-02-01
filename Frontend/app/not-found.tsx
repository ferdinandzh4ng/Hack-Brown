import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-bg px-4">
      <div className="text-center">
        <h1 className="font-heading text-2xl font-bold text-visa-blue mb-2">Page not found</h1>
        <p className="text-slate-muted mb-6">This page doesn&apos;t exist or was moved.</p>
        <Link
          href="/login"
          className="font-heading inline-flex items-center justify-center py-3 px-6 rounded-xl font-bold text-sm bg-visa-blue text-white hover:bg-visa-blue-dark transition-colors"
        >
          Go to sign in
        </Link>
      </div>
    </div>
  );
}
