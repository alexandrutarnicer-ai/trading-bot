"""
ai_engine.doctor — diagnostic rapid al surselor AI (fara MT5).

    python -m ai_engine.doctor

Verifica in special safety-net-ul Ollama: nu doar ca serverul raspunde, ci ca
poate RULA inferenta. Instalarile Ollama corupte (runner 'llama-server' lipsa)
raspund la /api/tags dar dau 500 la /api/chat — cauza clasica de "toate deciziile
sunt WAIT" cu botul aparent sanatos. Doctor-ul o prinde si da remedierea exacta.
"""

from __future__ import annotations

import sys

from ai_engine.config import load_config, load_keys
from ai_engine.providers import ProviderRegistry, build_provider


_OLLAMA_REMEDY = """\
  Remediere Ollama (safety-net-ul failover-ului):
   1. Reinstaleaza/actualizeaza Ollama: https://ollama.com/download
      (un update intrerupt lasa runner-ul 'llama-server' lipsa — cazul tipic).
   2. Verifica ca antivirusul nu a pus 'llama-server.exe' in carantina
      (Windows: %LOCALAPPDATA%\\Programs\\Ollama\\lib\\ollama\\).
   3. Reporneste Ollama, apoi confirma inferenta:
        ollama run <model> "ok"
   4. Reruleaza: python -m ai_engine.doctor
  Motorul AI functioneaza si degradat (failover pe surse cloud), dar fara Ollama
  ramane fara plasa de siguranta — repar-o cat mai repede."""


def main() -> int:
    cfg = load_config()
    keys = load_keys()
    reg = ProviderRegistry(cfg["providers"], keys)

    print("=== AI Engine — diagnostic surse AI ===\n")

    ok, detail = reg.default_probe()
    if ok:
        print("[safety-net] Ollama inferenta: OK")
    else:
        print("[safety-net] Ollama inferenta: DEFECT")
        print(f"  Cauza: {detail}\n")
        print(_OLLAMA_REMEDY)

    print("\n--- Test de contract per sursa (reachable -> auth -> JSON) ---")
    worst = 0 if ok else 1
    for name, spec in cfg["providers"].items():
        enabled = spec.get("enabled")
        try:
            prov = build_provider(name, spec, keys.get(name, ""))
            r = prov.test()
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "latency_s": 0, "detail": f"{type(e).__name__}: {e}"}
        flag = "OK  " if r["ok"] else "FAIL"
        state = "" if enabled else " (inactiv)"
        if not r["ok"] and enabled:
            worst = 1
        print(f"  [{flag}] {name}{state}  {r['latency_s']}s  {str(r.get('detail',''))[:120]}")

    print("\nRezumat:", "TOATE OK" if worst == 0 else "PROBLEME — vezi mai sus")
    return worst


if __name__ == "__main__":
    sys.exit(main())
