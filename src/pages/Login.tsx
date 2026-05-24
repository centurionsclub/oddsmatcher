import { useState } from "react";
import { Navigate } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/contexts/AuthContext";

const Login = () => {
  const { session } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (session) return <Navigate to="/" replace />;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setLoading(false);
    if (error) setError("Email o password errati.");
  };

  return (
    <div className="min-h-screen bg-[#0d1320] flex flex-col items-center justify-center px-4">
      <div className="mb-8 text-center">
        <img
          src="/logo-centurion.png"
          alt="Centurion Club"
          className="mx-auto mb-4 w-36 md:w-44"
        />
        <h1 className="text-3xl md:text-4xl font-bold text-[#c8922d]" style={{ fontFamily: "'Cinzel', serif", letterSpacing: "0.15em" }}>
          ODDSMATCHER
        </h1>
        <p className="text-slate-400 text-sm mt-1">Accedi con le tue credenziali</p>
      </div>

      <form onSubmit={handleLogin} className="bg-[#152033] border border-[#1e3050] rounded-xl shadow-2xl p-6 md:p-8 w-full max-w-sm">
        <div className="mb-4">
          <label className="block text-xs font-medium text-slate-400 mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            autoFocus
            placeholder="email@esempio.com"
            className="w-full bg-[#1a2535] border border-[#253347] text-white rounded px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40 placeholder-slate-500"
          />
        </div>
        <div className="mb-6">
          <label className="block text-xs font-medium text-slate-400 mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            placeholder="••••••••"
            className="w-full bg-[#1a2535] border border-[#253347] text-white rounded px-3 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#c8922d]/40 placeholder-slate-500"
          />
        </div>
        {error && <p className="text-red-400 text-xs mb-4 text-center">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-3 rounded font-bold text-sm bg-[#c8922d] text-white hover:bg-[#b07a24] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Accesso in corso…" : "ACCEDI"}
        </button>
      </form>
    </div>
  );
};

export default Login;
