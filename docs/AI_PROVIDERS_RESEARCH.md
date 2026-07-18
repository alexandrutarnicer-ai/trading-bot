# Surse AI gratuite — cercetare & recomandări pentru redundanță

**Data:** 2026-07-17 · **Autor:** Claude (Opus 4.8)

> ⚠️ **Notă:** limitele free-tier se schimbă des. Cifrele de mai jos sunt din cunoștințele mele (cutoff ian. 2026) și trebuie **verificate la înscriere**. Toate sursele recomandate sunt **compatibile OpenAI** → se adaugă în motorul nostru cu adaptorul existent `openai_compatible` (doar `base_url` + cheie + model), fără cod nou.

## Contextul nostru

Surse configurate acum: `ollama` (local, safety-net), `gemini`, `groq`, `cerebras`, `mistral`, `openroute`, `hug1`, `hug2quen3`, `claude`, `chatgpt`. La diagnostic (2026-07-17): **doar 3–4 sănătoase** — groq rate-limited, hug1/hug2/openroute cu credite epuizate, gemini intermitent 503. Avem nevoie de **2–4 surse gratuite fiabile în plus** ca plasă de rezervă, ca să nu ajungem în situația „toate picate → WAIT la tot".

## Recomandări (ordonate după fiabilitate/valoare)

| Sursă | Free tier | Rate limit | Modele | API | ✅ Avantaje | ⚠️ Dezavantaje |
|-------|-----------|-----------|--------|-----|-------------|----------------|
| **GitHub Models** ⭐ | Gratuit (preview) | Moderat/zi per model | GPT-4o, GPT-4o-mini, Llama 3.x, Mistral, Phi-4, DeepSeek | OpenAI-compat (`models.inference.ai.azure.com`) | Azure-backed = **foarte fiabil**; modele top (GPT-4o) gratis; doar un PAT GitHub | Limite zilnice pe preview; poate deveni plătit |
| **Cloudflare Workers AI** ⭐ | ~10k „neurons"/zi gratis | Generos | Llama 3.3, Mistral, Qwen, Gemma, DeepSeek | OpenAI-compat | Infrastructură foarte stabilă; latență mică; multe modele open | Neuron accounting; unele modele mai mici |
| **SambaNova Cloud** ⭐ | Gratuit cu cheie | Rezonabil | Llama 3.1/3.3 (8B–405B), Qwen | OpenAI-compat | **Cel mai RAPID** pe Llama mari; 405B gratis | Doar familia Llama/Qwen; poate cere waitlist |
| **NVIDIA NIM** (build.nvidia.com) | Credite gratuite generoase | Bun | Llama, Mistral, Nemotron, DeepSeek, Qwen | OpenAI-compat | Multe modele; infra NVIDIA fiabilă | Creditele se pot epuiza; înscriere |
| **Together AI** | ~$1–5 credit + modele free | Bun | Llama, Qwen, Mistral, DeepSeek | OpenAI-compat | Catalog mare; câteva modele complet free | Creditul se termină; apoi plătit |
| **Scaleway Generative** | Beta gratuit | Moderat | Llama, Mistral | OpenAI-compat | EU-based (latență bună din RO) | Beta — disponibilitate variabilă |
| **OpenRouter** (deja) | Modele `:free` | Strict pe free | Multe (rotativ) | OpenAI-compat | Un singur cont → multe modele | Modelele `:free` se schimbă/rate-limit dur (deja văzut 402) |

## Recomandarea mea concretă

Pentru **redundanță maximă cu efort minim**, adaugă în această ordine (toate `openai_compatible`):

1. **GitHub Models** — cea mai fiabilă sursă gratuită de modele top (GPT-4o-mini), backing Azure. Prima alegere de rezervă.
2. **Cloudflare Workers AI** — infra foarte stabilă, cotă zilnică generoasă, Llama 3.3 / Qwen.
3. **SambaNova Cloud** — viteză excelentă pe Llama mari, bun pentru rolurile care cer analiză rapidă.

Cu aceste 3 + `cerebras`/`mistral` care merg deja + `ollama` (local, mereu sus), ai **6 surse independente** → practic imposibil ca „toate să pice" simultan.

### Cum le adaugi (fără cod)
Tab **AI Engine → Surse AI → Adaugă sursă**:
- Tip: `OpenAI-compatibil`
- `base_url`:
  - GitHub Models: `https://models.inference.ai.azure.com`
  - Cloudflare: `https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/v1`
  - SambaNova: `https://api.sambanova.ai/v1`
- Model: apasă **Descoperă** (populează lista live) sau tastează (ex: `gpt-4o-mini`, `Meta-Llama-3.3-70B-Instruct`, `@cf/meta/llama-3.3-70b-instruct`)
- Cheie: PAT/API key de la fiecare
- Apoi **Testează** (sau **🩺 Testează sursele**) și **Activează**.

### Igienă surse (recomandare imediată)
`hug1`, `hug2quen3`, `openroute` au **creditele epuizate** (402) — le poți **dezactiva** din UI ca să nu mai consume câte o încercare la fiecare revenire din pauză (cascada le sare oricum, dar dezactivarea e mai curată). Distribuie rolurile pe sursele sănătoase (cerebras/mistral) + adaugă 1–2 din recomandările de sus.

## Principiu de diversificare

Pentru independența opiniilor în modul multi-council, ideal: **furnizori pe infrastructuri diferite** (Azure/GitHub, Cloudflare, SambaNova, Google/Gemini, local/Ollama) — dacă unul are un incident, ceilalți nu sunt afectați. Evită să pui toate rolurile pe același furnizor.
