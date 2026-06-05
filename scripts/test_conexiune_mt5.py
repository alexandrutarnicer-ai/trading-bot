"""
Test de conectare MT5 <-> Python  (IC Markets demo)
----------------------------------------------------
Ce face scriptul:
  1. Se conecteaza la terminalul MT5 (care trebuie sa fie DESCHIS si LOGAT).
  2. Afiseaza versiunea, info despre terminal si despre contul tau.
  3. Cauta simbolurile de indici (numele exact difera de la broker la broker).
  4. Afiseaza pretul curent (bid/ask) pentru un index.

Inainte sa rulezi:
  - MT5 desktop trebuie sa fie deschis si logat pe contul demo.
  - Tools > Options > Expert Advisors > "Allow algorithmic trading" bifat.
  - pip install MetaTrader5

Rulare:  python test_conexiune_mt5.py
"""

import MetaTrader5 as mt5

# --- 1. Conectare la terminal ---------------------------------------------
# Daca terminalul e deja deschis si logat, initialize() se ataseaza la el.
if not mt5.initialize():
    print("EROARE la initialize():", mt5.last_error())
    print("Verifica: MT5 e deschis? esti logat? Python e 64-bit?")
    quit()

print("Conectare reusita.\n")

# --- (Optional) login explicit --------------------------------------------
# Daca terminalul NU e logat, poti decomenta si completa mai jos.
# NU pune parola intr-un fisier pe care il distribui.
#
# LOGIN    = 52906173
# PASSWORD = "PAROLA_TA_DE_DEMO"
# SERVER   = "ICMarketsEU-Demo"
# if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
#     print("Login esuat:", mt5.last_error())
#     mt5.shutdown()
#     quit()

# --- 2. Info terminal si cont ---------------------------------------------
print("Versiune MT5:", mt5.version())

acc = mt5.account_info()
if acc is not None:
    print("\n--- CONT ---")
    print("  Login   :", acc.login)
    print("  Server  :", acc.server)
    print("  Valuta  :", acc.currency)
    print("  Balanta :", acc.balance)
    print("  Equity  :", acc.equity)
    print("  Levier  : 1:", acc.leverage, sep="")

# --- 3. Descopera simbolurile de forex -----------------------------------
# Cautam fix perechile pe care vrei sa le testezi.
# (numele real poate avea un sufix, gen "EURUSD.r" - de aceea cautam "contine")
chei = ["EURUSD", "GBPUSD", "GBPJPY"]
toate = mt5.symbols_get()
print("\n--- PERECHI FOREX GASITE ---")
gasite = []
for s in toate:
    nume = s.name.upper()
    if any(k in nume for k in chei):
        gasite.append(s.name)
        print(" ", s.name, "  |  descriere:", s.description)

if not gasite:
    print("  Nu am gasit perechile cautate cu numele standard.")
    print("  Total simboluri disponibile:", len(toate))
    print("  (verifica in Market Watch numele exact, poate are sufix)")

# --- 4. Pretul curent pentru primul index gasit ---------------------------
if gasite:
    simbol = gasite[0]
    mt5.symbol_select(simbol, True)  # asigura ca e vizibil in Market Watch
    tick = mt5.symbol_info_tick(simbol)
    if tick:
        print(f"\n--- PRET CURENT pentru {simbol} ---")
        print("  Bid:", tick.bid)
        print("  Ask:", tick.ask)
        print("  Spread (puncte):", round((tick.ask - tick.bid), 5))

# --- 5. Inchidere ----------------------------------------------------------
mt5.shutdown()
print("\nGata. Conexiunea functioneaza daca ai vazut datele contului mai sus.")
