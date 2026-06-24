// Specificații aproximative per piată pentru calculul lotajului minim (ICMarketsEU)
// pip_val = USD per pip per lot standard, vol_min = lot minim broker
// typ_sl  = SL tipic estimat în pips/puncte pentru această strategie
// Valorile se schimbă cu cursul valutar — sunt estimări, nu valori exacte.

export interface MarketSpec {
  volMin:     number;   // lot minim broker
  pipVal:     number;   // USD per pip per lot
  typSl:      number;   // SL tipic estimat (pips / puncte)
  minCapital: number;   // capital minim recomandat (USD) — 3× marja unui trade la lot minim
}

export const MARKET_SPECS: Record<string, MarketSpec> = {
  // Forex majore — pip = 0.0001, vol_min = 0.01 loturi
  EURUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25,    minCapital: 150 },
  GBPUSD: { volMin: 0.01, pipVal: 10.0, typSl: 30,    minCapital: 200 },
  USDCHF: { volMin: 0.01, pipVal: 11.0, typSl: 40,    minCapital: 150 },
  USDCAD: { volMin: 0.01, pipVal: 7.5,  typSl: 30,    minCapital: 150 },
  AUDUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25,    minCapital: 100 },
  NZDUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25,    minCapital: 100 },
  // Cross JPY — pip = 0.01
  EURJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30,    minCapital: 150 },
  USDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30,    minCapital: 150 },
  AUDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30,    minCapital: 100 },
  NZDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30,    minCapital: 150 },
  GBPJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 40,    minCapital: 200 },
  CHFJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 40,    minCapital: 150 },
  // Crosses EUR/GBP
  EURCAD: { volMin: 0.01, pipVal: 7.25, typSl: 30,    minCapital: 150 },
  GBPCAD: { volMin: 0.01, pipVal: 7.25, typSl: 35,    minCapital: 200 },
  EURAUD: { volMin: 0.01, pipVal: 6.4,  typSl: 35,    minCapital: 150 },
  GBPAUD: { volMin: 0.01, pipVal: 6.4,  typSl: 40,    minCapital: 200 },
  AUDCAD: { volMin: 0.01, pipVal: 7.25, typSl: 25,    minCapital: 100 },
  AUDNZD: { volMin: 0.01, pipVal: 6.0,  typSl: 25,    minCapital: 100 },
  // Indici — pip = 1 punct, vol_min = 0.1 loturi (ICMarketsEU)
  GER40:  { volMin: 0.1,  pipVal: 1.08, typSl: 200,   minCapital: 250 },
  DE40:   { volMin: 0.1,  pipVal: 1.08, typSl: 200,   minCapital: 250 },
  US30:   { volMin: 0.1,  pipVal: 1.0,  typSl: 200,   minCapital: 400 },
  UK100:  { volMin: 0.1,  pipVal: 1.25, typSl: 150,   minCapital: 300 },
  US500:  { volMin: 0.1,  pipVal: 1.0,  typSl: 30,    minCapital: 150 },
  NAS100: { volMin: 0.1,  pipVal: 1.0,  typSl: 100,   minCapital: 200 },
  // Crypto
  BTCUSD: { volMin: 0.01, pipVal: 0.01, typSl: 50000, minCapital: 150 },
  ETHUSD: { volMin: 0.01, pipVal: 0.01, typSl: 5000,  minCapital: 100 },
  XRPUSD: { volMin: 0.01, pipVal: 0.01, typSl: 2000,  minCapital: 100 },
  // Metale — pip=1pt ($1 price move), pip_value=$100/pip/lot standard (100 oz)
  XAUUSD: { volMin: 0.01, pipVal: 100.0, typSl: 10,   minCapital: 1000 },
};

export interface OvershootInfo {
  intendedRisk: number;
  actualRisk:   number;
  factor:       number;
  volMin:       number;
}

/** Returnează null dacă nu există lotaj minim issue, altfel returnează detalii. */
export function calcOvershoot(
  capitalPerMarket: number,
  riskPct: number,
  spec: MarketSpec,
): OvershootInfo | null {
  if (capitalPerMarket <= 0 || riskPct <= 0) return null;
  const intendedRisk = capitalPerMarket * riskPct;
  const rawLots      = intendedRisk / (spec.typSl * spec.pipVal);
  if (rawLots >= spec.volMin) return null;
  const actualRisk = spec.volMin * spec.typSl * spec.pipVal;
  return {
    intendedRisk,
    actualRisk,
    factor: actualRisk / intendedRisk,
    volMin: spec.volMin,
  };
}
