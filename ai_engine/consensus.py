"""
ai_engine.consensus — combinarea opiniilor mai multor consilii AI (Feature:
Multi-Council Consensus).

Un "consiliu" = dezbaterea de roluri (Technical → Macro → Risk → [Quant] →
[Devil's Advocate] → Head Trader) rulata pe O SINGURA sursa AI, ca sa fie o
opinie independenta. Pana la 3 consilii, fiecare pe alta sursa, analizeaza
acelasi trade; aici le combinam intr-un verdict unic.

STRATEGIA DE CONSENS (aleasa: media increderilor efective + veto absolut):
  - fiecare consiliu produce: approved (head approve SI fara veto valid) + confidence
  - `effective` = confidence daca consiliul aproba, altfel 0 (dizidenta trage media in jos)
  - orice VETO HARD valid (NEWS_IMMINENT/EXTREME_VOL/WEEKEND_GAP/BAD_GEOMETRY...)
    de la ORICE consiliu participant → respingere absoluta (siguranta inainte de toate)
  - altfel: APROBAT ⟺ media(effective) >= prag

De ce media (nu ponderare/vot majoritar): e cea mai explicabila, nu introduce
ponderi necalibrate (nu avem inca outcome-uri reale ca sa le justificam), face
dizidenta sa conteze (un consiliu care respinge aduce 0 la medie) si — critic —
se REDUCE EXACT la comportamentul cu un singur consiliu de dinainte de feature
(media unui singur numar = numarul insusi). `combine` e o functie pura, testabila
fara MT5/LLM; strategia poate fi schimbata ulterior fara sa atinga apelantii.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CouncilOpinion:
    """Opinia unui singur consiliu despre daca trade-ul ar trebui sa continue."""

    source: str                          # numele sursei AI pe care a rulat consiliul
    approved: bool = False               # head approve SI fara veto valid
    confidence: int | None = None        # 0-100; None daca consiliul nu a produs verdict
    hard_veto: str | None = None         # cod de veto valid (respingere absoluta) sau None
    error: str | None = None             # motivul indisponibilitatii, daca a esuat
    reason: str = ""                     # rezumatul (head trader-ului)
    duration_s: float = 0.0
    transcript: dict = field(default_factory=dict)
    fallback_from: str | None = None     # daca sursa a fost substituita (mod distribuit pe roluri)

    @property
    def participated(self) -> bool:
        """A produs un verdict utilizabil (nu a esuat)."""
        return self.error is None and self.confidence is not None

    @property
    def effective_confidence(self) -> int:
        """Increderea care conteaza la consens: 0 pentru un consiliu care respinge."""
        if not self.participated:
            return 0
        return int(self.confidence) if self.approved else 0


@dataclass
class ConsensusVerdict:
    """Rezultatul combinarii opiniilor consiliilor."""

    approved: bool
    consensus_confidence: float | None   # media increderilor efective (participante)
    threshold: int
    n_participating: int                 # consilii care au produs un verdict
    n_requested: int                     # consilii cerute (enabled)
    n_approving: int                     # consilii participante care aproba individual
    sources: list[str]                   # sursele consiliilor participante
    veto_code: str | None
    reason: str
    all_failed: bool                     # niciun consiliu nu a produs verdict
    per_council: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "approved":             self.approved,
            "consensus_confidence": self.consensus_confidence,
            "threshold":            self.threshold,
            "n_participating":      self.n_participating,
            "n_requested":          self.n_requested,
            "n_approving":          self.n_approving,
            "sources":              list(self.sources),
            "veto_code":            self.veto_code,
            "reason":               self.reason,
            "all_failed":           self.all_failed,
            "councils":             self.per_council,
        }


def _slim(o: CouncilOpinion) -> dict:
    """Rezumat JSON-safe al unei opinii, pentru jurnal/UI (fara transcriptul mare)."""
    return {
        "source":        o.source,
        "approved":       bool(o.approved),
        "confidence":     o.confidence,
        "effective":      (o.effective_confidence if o.participated else None),
        "veto_code":      o.hard_veto,
        "error":          o.error,
        "reason":         (o.reason or "")[:300],
        "duration_s":     round(o.duration_s, 1),
        "fallback_from":  o.fallback_from,
    }


def combine(opinions: list[CouncilOpinion], threshold: int) -> ConsensusVerdict:
    """
    Combina opiniile consiliilor in verdictul de consens (strategie: media
    increderilor efective + veto absolut). Pura — fara efecte secundare.

    Un singur consiliu → verdictul e identic cu regula de dinainte de feature:
    `effective = confidence daca aproba altfel 0`; aprobat ⟺ effective >= prag.
    """
    n_requested = len(opinions)
    participating = [o for o in opinions if o.participated]
    per_council = [_slim(o) for o in opinions]

    if not participating:
        # niciun consiliu disponibil — apelantul decide politica (fail-open/fail-safe)
        return ConsensusVerdict(
            approved=False, consensus_confidence=None, threshold=threshold,
            n_participating=0, n_requested=n_requested, n_approving=0, sources=[],
            veto_code=None, reason="Niciun consiliu AI disponibil.",
            all_failed=True, per_council=per_council)

    # 1. Veto absolut: orice consiliu participant cu veto hard valid → respins.
    veto = next((o for o in participating if o.hard_veto), None)
    if veto is not None:
        return ConsensusVerdict(
            approved=False, consensus_confidence=None, threshold=threshold,
            n_participating=len(participating), n_requested=n_requested,
            n_approving=sum(1 for o in participating if o.approved),
            sources=[o.source for o in participating], veto_code=veto.hard_veto,
            reason=(f"[VETO {veto.hard_veto} — consiliul «{veto.source}»] respins "
                    "de siguranta, indiferent de restul consensului."),
            all_failed=False, per_council=per_council)

    # 2. Media increderilor efective vs prag.
    effective = [o.effective_confidence for o in participating]
    mean = sum(effective) / len(effective)
    approved = mean >= threshold
    n_approve = sum(1 for o in participating if o.approved)
    n = len(participating)
    reason = (f"Consens {n} consili{'i' if n != 1 else 'u'}: "
              f"{mean:.0f}% {'>=' if approved else '<'} prag {threshold}% "
              f"({n_approve}/{n} de acord · surse: {', '.join(o.source for o in participating)}).")
    return ConsensusVerdict(
        approved=approved, consensus_confidence=round(mean, 1), threshold=threshold,
        n_participating=n, n_requested=n_requested, n_approving=n_approve,
        sources=[o.source for o in participating], veto_code=None,
        reason=reason, all_failed=False, per_council=per_council)


def resolve_sources(*candidates: str | None) -> tuple[list[str], list[str]]:
    """
    Lista ordonata, deduplicata, de surse de consiliu. Intrarile None/goale sunt
    ignorate; duplicatele sunt raportate separat (pentru validarea din UI/API:
    doua consilii nu au voie sa foloseasca aceeasi sursa — punctul intreg e sa
    obtii opinii independente, nu aceeasi analiza de doua ori).

    Returneaza (surse_distincte, duplicate_ignorate).
    """
    seen: list[str] = []
    dropped: list[str] = []
    for c in candidates:
        if not c:
            continue
        s = str(c).strip()
        if not s:
            continue
        if s in seen:
            dropped.append(s)
        else:
            seen.append(s)
    return seen, dropped
