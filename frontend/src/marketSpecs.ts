// Specificații aproximative per piată pentru calculul lotajului minim (ICMarketsEU)
// pip_val = USD per pip per lot standard, vol_min = lot minim broker
// typ_sl  = SL tipic estimat în pips/puncte pentru această strategie
// Valorile se schimbă cu cursul valutar — sunt estimări, nu valori exacte.

export interface MarketSpec {
  volMin:  number;   // lot minim broker
  pipVal:  number;   // USD per pip per lot
  typSl:   number;   // SL tipic estimat (pips / puncte)
}

export const MARKET_SPECS: Record<string, MarketSpec> = {
  // Forex majore — pip = 0.0001, vol_min = 0.01 loturi
  EURUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25 },
  GBPUSD: { volMin: 0.01, pipVal: 10.0, typSl: 30 },
  USDCHF: { volMin: 0.01, pipVal: 11.0, typSl: 40 },
  USDCAD: { volMin: 0.01, pipVal: 7.5,  typSl: 30 },
  AUDUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25 },
  NZDUSD: { volMin: 0.01, pipVal: 10.0, typSl: 25 },
  // Cross JPY — pip = 0.01, pip_val depinde de JPY/USD
  EURJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30 },
  USDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30 },
  AUDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30 },
  NZDJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 30 },
  GBPJPY: { volMin: 0.01, pipVal: 6.5,  typSl: 40 },
  // Indici — pip = 1 punct, vol_min = 0.1 loturi (ICMarketsEU)
  GER40:  { volMin: 0.1,  pipVal: 1.14, typSl: 200 },
  DE40:   { volMin: 0.1,  pipVal: 1.14, typSl: 200 },
  US30:   { volMin: 0.1,  pipVal: 1.0,  typSl: 200 },
  UK100:  { volMin: 0.1,  pipVal: 1.25, typSl: 150 },
  US500:  { volMin: 0.1,  pipVal: 1.0,  typSl: 30  },
  NAS100: { volMin: 0.1,  pipVal: 1.0,  typSl: 100 },
  // Crypto — pip = tick_size (0.01 pentru BTC), vol_min = 0.01
  BTCUSD: { volMin: 0.01, pipVal: 0.01, typSl: 50000 },
  ETHUSD: { volMin: 0.01, pipVal: 0.01, typSl: 5000  },
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
