interface Props {
  text: string;
  wide?: boolean;
  position?: "above" | "below";
}

export function InfoTooltip({ text, wide, position = "above" }: Props) {
  const above = position === "above";
  return (
    <span className="relative group inline-flex items-center align-middle">
      <span className="w-3.5 h-3.5 rounded-full border border-slate-600 text-[8px] text-slate-500 flex items-center justify-center cursor-help hover:border-slate-400 hover:text-slate-300 transition-colors ml-1 select-none leading-none">
        i
      </span>
      <span
        className={`
          absolute left-1/2 -translate-x-1/2
          ${above ? "bottom-full mb-2" : "top-full mt-2"}
          ${wide ? "w-72" : "w-56"}
          bg-slate-900 border border-slate-600 text-xs text-slate-300
          rounded-lg px-3 py-2 shadow-xl z-50
          invisible group-hover:visible opacity-0 group-hover:opacity-100
          transition-opacity pointer-events-none
        `}
      >
        {text}
        {above
          ? <span className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-slate-600" />
          : <span className="absolute left-1/2 -translate-x-1/2 bottom-full w-0 h-0 border-x-4 border-x-transparent border-b-4 border-b-slate-600" />
        }
      </span>
    </span>
  );
}
