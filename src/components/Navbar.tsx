import { Link, useLocation } from "react-router-dom";

const navItems = [
  { path: "/", label: "ODDSMATCHER" },
  { path: "/punta-banca", label: "PUNTA → BANCA" },
  { path: "/punta-punta", label: "PUNTA → PUNTA" },
  { path: "/punta-3vie", label: "PUNTA → 3 VIE" },
];

export function Navbar() {
  const location = useLocation();

  return (
    <nav className="bg-[#080d17] shadow-md border-b border-[#1e3050]">
      <div className="max-w-[1600px] mx-auto px-4 flex items-center h-12">
        <div className="flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`px-4 py-2 text-[13px] font-semibold tracking-wide transition-colors rounded-sm ${
                  isActive
                    ? "text-[#c8922d] bg-[#0f1a2e]"
                    : "text-white hover:text-white hover:bg-[#0f1a2e]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
