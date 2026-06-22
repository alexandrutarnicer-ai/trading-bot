interface Props {
  src: string;
  alt: string;
  position?: "above" | "below";
}

export function ImageTooltip({ src, alt, position = "above" }: Props) {
  const above = position === "above";
  return (
    <span className="relative group inline-flex items-center align-middle">
      <span className="w-3.5 h-3.5 rounded-full border border-slate-600 text-[8px] text-slate-500 flex items-center justify-center cursor-help hover:border-blue-400 hover:text-blue-300 transition-colors ml-1 select-none leading-none">
        ?
      </span>
      <span
        className={`
          absolute left-0
          ${above ? "bottom-full mb-2" : "top-full mt-2"}
          w-[420px] bg-slate-900 border border-slate-600
          rounded-lg p-1.5 shadow-2xl z-[100]
          invisible group-hover:visible opacity-0 group-hover:opacity-100
          transition-opacity pointer-events-none
        `}
      >
        <img src={src} alt={alt} className="w-full rounded" />
        {above
          ? <span className="absolute left-2 top-full w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-slate-600" />
          : <span className="absolute left-2 bottom-full w-0 h-0 border-x-4 border-x-transparent border-b-4 border-b-slate-600" />
        }
      </span>
    </span>
  );
}
