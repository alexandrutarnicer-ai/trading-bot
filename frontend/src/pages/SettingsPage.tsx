import { Mt5Status } from "../components/Mt5Status";
import { TelegramSettings } from "../components/TelegramSettings";
import { TelegramBridgeCard } from "../components/TelegramBridgeCard";
import { MatrixSettings } from "../components/MatrixSettings";
import { LiveTradingCard } from "../components/LiveTradingCard";
import { GlobalSettingsCard } from "../components/GlobalSettingsCard";
import { TimezoneSelector } from "./ProfilePage";

/**
 * Settings — setarile GLOBALE ale aplicatiei, comune pentru Custom Engine + AI Engine:
 * conexiune MT5, Telegram (+ punte/Matrix), Trading LIVE, Setari Globale
 * (protectie capital, circuit breaker, vineri, stiri, pozitii simultane, filtru AI),
 * fus orar. Configurarea pietelor/strategiilor e in tab-ul Custom Engine.
 */
export function SettingsPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-6 space-y-5">
      <Mt5Status />
      <LiveTradingCard />
      <GlobalSettingsCard />
      <TelegramSettings />
      <TelegramBridgeCard />
      <MatrixSettings />
      <TimezoneSelector />
    </div>
  );
}
