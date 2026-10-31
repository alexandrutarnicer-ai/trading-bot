/**
 * Identitatea „No Trading”: un „N” construit din două lumânări de chart (corp + fitil) unite de o
 * diagonală ascendentă — trading algoritmic, fără intervenție manuală. Același desen ca
 * public/favicon.svg (ține-le sincron).
 */
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="nt-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1e3a8a" />
          <stop offset="1" stopColor="#0e7490" />
        </linearGradient>
        <linearGradient id="nt-fg" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#34d399" />
          <stop offset="1" stopColor="#67e8f9" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="url(#nt-bg)" />
      {/* lumanarea stanga: fitil + corp */}
      <line x1="10" y1="6" x2="10" y2="26" stroke="#a7f3d0" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="7.5" y="10" width="5" height="13" rx="1.2" fill="url(#nt-fg)" />
      {/* lumanarea dreapta */}
      <line x1="22" y1="6" x2="22" y2="26" stroke="#a7f3d0" strokeWidth="1.4" strokeLinecap="round" />
      <rect x="19.5" y="9" width="5" height="13" rx="1.2" fill="url(#nt-fg)" />
      {/* diagonala N */}
      <path d="M12.5 11 L19.5 21" stroke="#ecfeff" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function BrandLockup() {
  return (
    <span className="flex items-center gap-2 mr-5 select-none">
      <BrandMark size={24} />
      <span className="leading-none">
        <span className="block text-sm font-extrabold tracking-wide text-white">
          No<span className="text-cyan-300">Trading</span>
        </span>
        <span className="block text-[9px] uppercase tracking-[0.18em] text-slate-500">algorithmic engines</span>
      </span>
    </span>
  );
}
