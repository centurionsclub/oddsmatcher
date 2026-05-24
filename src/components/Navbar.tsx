import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { path: "/punta-banca", label: "PUNTA → BANCA" },
  { path: "/punta-punta", label: "PUNTA → PUNTA" },
  { path: "/punta-3vie", label: "PUNTA → 3 VIE" },
];

export function Navbar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <nav className="bg-[#080d17] shadow-md border-b border-[#1e3050]">
      {/* Desktop */}
      <div className="max-w-[1600px] mx-auto px-4 hidden md:flex items-center justify-between h-12">
        <div className="flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`px-4 py-2 text-[13px] font-semibold tracking-wide transition-colors rounded-sm ${
                  isActive ? "text-[#c8922d] bg-[#0f1a2e]" : "text-white hover:text-white hover:bg-[#0f1a2e]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
        {user && (
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-[#1a2535] border border-[#253347] flex items-center justify-center text-slate-300" title={user.email}>
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
              </svg>
            </div>
            <button
              onClick={handleSignOut}
              className="px-3 py-1.5 text-xs font-semibold text-slate-300 border border-[#253347] rounded hover:border-red-500/60 hover:text-red-400 transition-colors"
            >
              Esci
            </button>
          </div>
        )}
      </div>

      {/* Mobile */}
      <div className="md:hidden px-4 flex items-center justify-between h-12">
        <span className="text-[#c8922d] font-bold text-lg" style={{ fontFamily: "'Cinzel', serif", letterSpacing: "0.12em" }}>ODDSMATCHER</span>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="text-white p-2 rounded focus:outline-none"
          aria-label="Menu"
        >
          {menuOpen ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile dropdown */}
      {menuOpen && (
        <div className="md:hidden border-t border-[#1e3050] bg-[#080d17]">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setMenuOpen(false)}
                className={`block px-4 py-3 text-sm font-semibold tracking-wide border-b border-[#1e3050] ${
                  isActive ? "text-[#c8922d] bg-[#0f1a2e]" : "text-white hover:bg-[#0f1a2e]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          {user && (
            <div className="px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-400">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 12c2.7 0 4.8-2.1 4.8-4.8S14.7 2.4 12 2.4 7.2 4.5 7.2 7.2 9.3 12 12 12zm0 2.4c-3.2 0-9.6 1.6-9.6 4.8v2.4h19.2v-2.4c0-3.2-6.4-4.8-9.6-4.8z"/>
                </svg>
                <span className="text-xs truncate max-w-[180px]">{user.email}</span>
              </div>
              <button
                onClick={handleSignOut}
                className="px-3 py-1.5 text-xs font-semibold text-red-400 border border-red-500/40 rounded"
              >
                Esci
              </button>
            </div>
          )}
        </div>
      )}
    </nav>
  );
}
