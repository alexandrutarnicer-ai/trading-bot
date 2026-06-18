import { useState } from "react";
import { useTelegramConfig, useSaveTelegram, useClearTelegram, useTestTelegram } from "../api/hooks";
import { InfoTooltip } from "./InfoTooltip";

const TG_GUIDE = [
  {
    step: "1. Creează un bot Telegram",
    items: [
      "Deschide Telegram și caută @BotFather",
      'Trimite comanda /newbot',
      "Alege un nume și un username (ex: MyTradingBot_bot)",
      "Copiază token-ul primit (format: 1234567890:ABCdef...GHIjkl)",
    ],
  },
  {
    step: "2. Obține Chat ID",
    items: [
      "Pornește conversația cu bot-ul tău (caută username-ul în Telegram)",
      "Trimite orice mesaj bot-ului",
      'Accesează în browser: https://api.telegram.org/bot{TOKEN}/getUpdates',
      'Chat ID-ul apare în câmpul "chat" → "id" (număr, poate fi negativ pentru grupuri)',
      "Alternativ: caută @userinfobot și trimite /start pentru a-ți vedea propriul ID",
    ],
  },
];

export function TelegramSettings() {
  const { data: cfg, isLoading } = useTelegramConfig();
  const save  = useSaveTelegram();
  const clear = useClearTelegram();

  const test  = useTestTelegram();

  const [open, setOpen]           = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [token, setToken]         = useState("");
  const [chatId, setChatId]       = useState("");
  const [saved, setSaved]         = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [testOk, setTestOk]       = useState<boolean | null>(null);
  const [testErr, setTestErr]     = useState<string | null>(null);

  const handleSave = async () => {
    setError(null);
    setSaved(false);
    try {
      await save.mutateAsync({ token, chat_id: chatId });
      setSaved(true);
      setToken("");
      setChatId("");
      setTimeout(() => setSaved(false), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Eroare la salvare");
    }
  };

  const handleClear = async () => {
    await clear.mutateAsync();
    setSaved(false);
    setTestOk(null);
    setTestErr(null);
  };

  const handleTest = async () => {
    setTestOk(null);
    setTestErr(null);
    try {
      await test.mutateAsync();
      setTestOk(true);
      setTimeout(() => setTestOk(null), 5000);
    } catch (e: unknown) {
      setTestErr(e instanceof Error ? e.message : "Eroare la trimitere");
    }
  };

  return (
    <div className="bg-surface-card rounded-xl border border-surface-border overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-border/20 transition-colors text-left"
      >
        <span className="text-sm font-semibold text-white flex-1">Notificări Telegram</span>
        {isLoading ? (
          <span className="text-xs text-slate-600">Se încarcă...</span>
        ) : cfg?.configured ? (
          <span className="text-xs px-2 py-0.5 rounded-full bg-profit/20 text-profit">Configurat</span>
        ) : (
          <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-400">Neconfigurat</span>
        )}
        <span className="text-slate-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-surface-border px-4 py-4 space-y-4">
          {/* Status curent */}
          {cfg?.configured && (
            <div className="bg-profit/10 border border-profit/20 rounded-lg p-3 space-y-2.5">
              <div className="flex items-start justify-between gap-3">
                <div className="text-xs space-y-0.5">
                  <div className="text-slate-300 font-medium">Telegram configurat</div>
                  <div className="text-slate-500">
                    Token: <span className="text-slate-400 font-mono">{cfg.token_masked}</span>
                  </div>
                  <div className="text-slate-500">
                    Chat ID: <span className="text-slate-400 font-mono">{cfg.chat_id}</span>
                  </div>
                </div>
                <button
                  onClick={handleClear}
                  disabled={clear.isPending}
                  className="text-xs px-2.5 py-1 rounded border border-loss/40 text-loss/70 hover:border-loss hover:text-loss transition-colors flex-shrink-0"
                >
                  Șterge
                </button>
              </div>

              {/* Test button row */}
              <div className="flex items-center gap-3 pt-0.5 border-t border-profit/10">
                <button
                  onClick={handleTest}
                  disabled={test.isPending}
                  className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors font-medium flex items-center gap-1.5"
                >
                  {test.isPending ? (
                    <><span className="animate-spin inline-block">⟳</span> Se trimite...</>
                  ) : (
                    <>📨 Trimite mesaj de test</>
                  )}
                </button>
                {testOk === true && (
                  <span className="text-xs text-profit flex items-center gap-1">
                    ✓ Mesaj trimis — verifică Telegram
                  </span>
                )}
                {testErr && (
                  <span className="text-xs text-loss">{testErr}</span>
                )}
              </div>
            </div>
          )}

          {/* Formular */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                {cfg?.configured ? "Actualizează credențialele" : "Adaugă credențiale"}
              </span>
              <InfoTooltip
                text="Token-ul și Chat ID-ul sunt stocate local în data/telegram_config.json. Nu sunt trimise nicăieri în afară de api.telegram.org."
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-xs text-slate-500">
                  Bot Token
                  <InfoTooltip text="Primit de la @BotFather. Format: 1234567890:ABCdef...GHIjkl" />
                </label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="1234567890:ABCdef..."
                  className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-slate-500">
                  Chat ID
                  <InfoTooltip text="ID-ul conversației cu bot-ul. Obținut din getUpdates sau @userinfobot. Poate fi negativ pentru grupuri." />
                </label>
                <input
                  type="text"
                  value={chatId}
                  onChange={(e) => setChatId(e.target.value)}
                  placeholder="-1001234567890"
                  className="w-full bg-surface border border-surface-border rounded px-2 py-1.5 text-xs text-white font-mono focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleSave}
                disabled={!token.trim() || !chatId.trim() || save.isPending}
                className="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 transition-colors font-medium"
              >
                {save.isPending ? "Se salvează..." : "Salvează"}
              </button>
              {saved && <span className="text-xs text-profit">✓ Salvat cu succes</span>}
              {error && <span className="text-xs text-loss">{error}</span>}
              <button
                onClick={() => setShowGuide((v) => !v)}
                className="ml-auto text-xs text-slate-500 hover:text-slate-300 underline transition-colors"
              >
                {showGuide ? "Ascunde ghidul" : "Cum obțin token-ul și Chat ID?"}
              </button>
            </div>
          </div>

          {/* Ghid pas cu pas */}
          {showGuide && (
            <div className="bg-surface rounded-xl border border-surface-border p-4 space-y-4">
              {TG_GUIDE.map((section) => (
                <div key={section.step} className="space-y-2">
                  <div className="text-xs font-semibold text-white">{section.step}</div>
                  <ol className="space-y-1">
                    {section.items.map((item, i) => (
                      <li key={i} className="flex gap-2 text-xs text-slate-400">
                        <span className="text-slate-600 flex-shrink-0">{i + 1}.</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
              <div className="text-xs text-slate-600 border-t border-surface-border pt-2">
                După salvare, repornește bot-ul pentru ca noile credențiale să fie active.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
