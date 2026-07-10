import { useState } from "react";
import { Bell, Trash2, CheckCheck, X, TrendingUp, ShieldAlert, Pause, Bot, BarChart2, Info } from "lucide-react";
import {
  useNotifications, useMarkNotificationsRead,
  useDeleteNotification, useClearNotifications,
} from "../api/hooks";
import type { NotificationItem } from "../api/types";

// ── Category config ───────────────────────────────────────────────────────────

const CATEGORY_META: Record<
  NotificationItem["category"],
  { label: string; icon: React.ReactNode; dot: string; bg: string; border: string }
> = {
  ai:      { label: "Filtru AI",   icon: <Bot        size={13} />,   dot: "bg-purple-400", bg: "bg-purple-500/10", border: "border-purple-500/20" },
  order:   { label: "Ordine",      icon: <TrendingUp size={13} />,   dot: "bg-profit",     bg: "bg-profit/10",  border: "border-profit/20"   },
  trade:   { label: "Tranzacții",  icon: <BarChart2  size={13} />,   dot: "bg-profit/70",  bg: "bg-profit/8",   border: "border-profit/15"   },
  signal:  { label: "Semnale",     icon: <Bell       size={13} />,   dot: "bg-blue-400",   bg: "bg-blue-500/10",border: "border-blue-500/20"  },
  news:    { label: "Știri",       icon: <ShieldAlert size={13} />,  dot: "bg-warn",       bg: "bg-warn/10",    border: "border-warn/20"     },
  session: { label: "Sesiuni",     icon: <Pause      size={13} />,   dot: "bg-slate-400",  bg: "bg-surface-border/30", border: "border-surface-border" },
  bot:     { label: "Bot",         icon: <Bot        size={13} />,   dot: "bg-blue-300",   bg: "bg-blue-500/8", border: "border-blue-500/15"  },
  system:  { label: "Sistem",      icon: <Info       size={13} />,   dot: "bg-slate-500",  bg: "bg-surface-border/20",border: "border-surface-border" },
};

const ALL_CATEGORIES = ["ai", "order", "trade", "signal", "news", "session", "bot", "system"] as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(iso: string) {
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  const time = d.toLocaleTimeString("ro-RO", { hour: "2-digit", minute: "2-digit" });
  if (isToday)     return `azi ${time}`;
  if (isYesterday) return `ieri ${time}`;
  return d.toLocaleDateString("ro-RO", { day: "2-digit", month: "short" }) + ` ${time}`;
}

function relTime(iso: string) {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60)   return "acum";
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400)return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}z`;
}

// ── Notification card ─────────────────────────────────────────────────────────

function NotifCard({
  item,
  onDelete,
}: {
  item: NotificationItem;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta  = CATEGORY_META[item.category] ?? CATEGORY_META.system;
  const lines = item.text_plain.split("\n").filter(Boolean);
  const title = lines[0] ?? "";
  const body  = lines.slice(1).join("\n");
  const hasBody = body.trim().length > 0;

  return (
    <div
      className={`relative group rounded-xl border px-4 py-3 transition-all ${meta.bg} ${meta.border} ${
        !item.read ? "ring-1 ring-inset ring-white/5" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Category icon + unread dot */}
        <div className="relative flex-shrink-0 mt-0.5">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center ${meta.bg} border ${meta.border} text-slate-300`}>
            {meta.icon}
          </div>
          {!item.read && (
            <span className={`absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full ${meta.dot} border border-surface`} />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className={`text-xs font-semibold leading-snug ${!item.read ? "text-white" : "text-slate-300"}`}>
              {title}
            </span>
            <span className="text-[10px] text-slate-500 flex-shrink-0">{relTime(item.time)}</span>
          </div>

          {hasBody && (
            <>
              {expanded ? (
                <pre className="text-[11px] text-slate-400 mt-1 whitespace-pre-wrap leading-relaxed font-sans">{body}</pre>
              ) : (
                <p className="text-[11px] text-slate-500 mt-0.5 truncate">{body.replace(/\n/g, " · ")}</p>
              )}
              <button
                onClick={() => setExpanded(e => !e)}
                className="text-[10px] text-blue-500 hover:text-blue-400 mt-0.5 transition-colors"
              >
                {expanded ? "Ascunde" : "Extinde"}
              </button>
            </>
          )}

          <div className="text-[9px] text-slate-600 mt-1">{fmtTime(item.time)}</div>
        </div>

        {/* Delete button */}
        <button
          onClick={() => onDelete(item.id)}
          className="flex-shrink-0 p-1 text-slate-600 hover:text-loss transition-colors opacity-0 group-hover:opacity-100"
        >
          <X size={13} />
        </button>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <Bell size={40} className="text-slate-700 mb-4" />
      <p className="text-slate-400 font-medium">Nicio notificare</p>
      <p className="text-slate-600 text-sm mt-1">
        Notificările apar automat la semnale, ordine, știri și schimbări de sesiune.
      </p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function NotificationsPage() {
  const [filterCat, setFilterCat] = useState<NotificationItem["category"] | "all">("all");
  const { data, isLoading } = useNotifications(200);
  const markRead    = useMarkNotificationsRead();
  const deleteNotif = useDeleteNotification();
  const clearAll    = useClearNotifications();

  const items  = data?.items ?? [];
  const unread = data?.unread ?? 0;

  const filtered = filterCat === "all"
    ? items
    : items.filter(n => n.category === filterCat);

  function handleClear() {
    if (items.length === 0) return;
    if (confirm(`Șterge toate ${items.length} notificările?`)) clearAll.mutate();
  }

  // Group by date for display
  type Group = { label: string; items: NotificationItem[] };
  const groups: Group[] = [];
  let lastLabel = "";
  for (const item of filtered) {
    const d    = new Date(item.time);
    const now  = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const yesterday = new Date(now); yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = d.toDateString() === yesterday.toDateString();
    const label = isToday ? "Azi" : isYesterday ? "Ieri"
      : d.toLocaleDateString("ro-RO", { weekday: "long", day: "numeric", month: "long" });

    if (label !== lastLabel) {
      groups.push({ label, items: [] });
      lastLabel = label;
    }
    groups[groups.length - 1].items.push(item);
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Bell size={16} className="text-blue-400" />
          <h1 className="text-sm font-semibold text-white">Notificări</h1>
          {unread > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 font-medium border border-blue-500/30">
              {unread} necitite
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {unread > 0 && (
            <button
              onClick={() => markRead.mutate()}
              className="flex items-center gap-1.5 text-[10px] px-2.5 py-1.5 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-white transition-colors"
            >
              <CheckCheck size={12} />
              Marchează citite
            </button>
          )}
          <button
            onClick={handleClear}
            disabled={items.length === 0}
            className="flex items-center gap-1.5 text-[10px] px-2.5 py-1.5 rounded-lg bg-surface-card border border-surface-border text-slate-400 hover:text-loss transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <Trash2 size={12} />
            Șterge tot
          </button>
        </div>
      </div>

      {/* Category filter tabs */}
      <div className="flex gap-1 flex-wrap">
        <button
          onClick={() => setFilterCat("all")}
          className={`text-[10px] px-2.5 py-1 rounded-lg transition-colors font-medium ${
            filterCat === "all"
              ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
              : "text-slate-500 hover:text-slate-300 border border-transparent"
          }`}
        >
          Toate {items.length > 0 ? `(${items.length})` : ""}
        </button>
        {ALL_CATEGORIES.map(cat => {
          const count = items.filter(n => n.category === cat).length;
          if (count === 0) return null;
          const meta = CATEGORY_META[cat];
          return (
            <button
              key={cat}
              onClick={() => setFilterCat(cat)}
              className={`flex items-center gap-1 text-[10px] px-2.5 py-1 rounded-lg transition-colors ${
                filterCat === cat
                  ? `${meta.bg} text-slate-200 border ${meta.border}`
                  : "text-slate-500 hover:text-slate-300 border border-transparent"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
              {meta.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 rounded-xl bg-surface-card animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-6">
          {groups.map(group => (
            <div key={group.label}>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-medium mb-2 px-1">
                {group.label}
              </div>
              <div className="space-y-2">
                {group.items.map(item => (
                  <NotifCard
                    key={item.id}
                    item={item}
                    onDelete={id => deleteNotif.mutate(id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
