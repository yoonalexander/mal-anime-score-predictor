import { useEffect, useMemo, useState } from "react";
import AnimeCard from "./components/AnimeCard";
import BackgroundParticles from "./components/BackgroundParticles";

// configure your API base via env or default
const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

async function fetchPredictions(apiBase, year, season) {
  const res = await fetch(`${apiBase}/season/${year}/${season}/predictions`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// fallback: if backend didn’t send image_url, fetch from Jikan
async function fetchCoverFor(malId) {
  try {
    const r = await fetch(`https://api.jikan.moe/v4/anime/${malId}`);
    if (!r.ok) return null;
    const j = await r.json();
    return (
      j?.data?.images?.webp?.large_image_url ||
      j?.data?.images?.jpg?.large_image_url ||
      j?.data?.images?.jpg?.image_url ||
      null
    );
  } catch {
    return null;
  }
}

export default function AnimePredictionsApp() {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [year, setYear] = useState("2025");
  const [season, setSeason] = useState("fall");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);

  const [query, setQuery] = useState("");
  const [sortByScore, setSortByScore] = useState(true);

  const seasons = ["winter", "spring", "summer", "fall"];

  const refresh = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await fetchPredictions(apiBase, year, season);

      // hydrate missing covers in parallel (limited)
      const augmented = await Promise.all(
        data.map(async (it) => {
          if (it.image_url) return it;
          const cover = await fetchCoverFor(it.mal_id);
          return { ...it, image_url: cover || null };
        })
      );

      setItems(augmented);
    } catch (e) {
      console.error(e);
      setError(e?.message || "Failed to fetch");
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = !q
      ? items
      : items.filter(
          (r) =>
            r.title?.toLowerCase().includes(q) ||
            String(r.mal_id).includes(q)
        );

    if (sortByScore) {
      rows = rows.slice().sort((a, b) => (b.pred_score ?? 0) - (a.pred_score ?? 0));
    }
    return rows;
  }, [items, query, sortByScore]);

  return (
    <div className="relative min-h-screen isolate">
      <BackgroundParticles />

      {/* Header / nav */}
      <header className="sticky top-0 z-50 bg-white/70 dark:bg-slate-900/70 backdrop-blur">
        <div className="mb-6 rounded-3xl border border-border bg-gradient-to-b from-background to-muted p-6">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold">MAL Anime Score Predictions</h1>

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <input
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                className="min-w-[320px] rounded-xl border border-input bg-background px-3 py-2 text-sm"
                placeholder="API base (e.g., http://127.0.0.1:8000)"
              />
              <input
                value={year}
                onChange={(e) => setYear(e.target.value)}
                className="w-24 rounded-xl border border-input bg-background px-3 py-2 text-sm"
                placeholder="Year"
              />
              <select
                value={season}
                onChange={(e) => setSeason(e.target.value)}
                className="w-28 rounded-xl border border-input bg-background px-3 py-2 text-sm"
              >
                {seasons.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>

              <button
                onClick={refresh}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90"
                title="Refresh"
              >
                Refresh
              </button>

              <button
                onClick={() => {
                  // quick CSV export of current filtered rows
                  const rows = filtered.map((r) => ({
                    mal_id: r.mal_id,
                    title: r.title,
                    year: r.year,
                    season: r.season,
                    pred_score: r.pred_score,
                    image_url: r.image_url || "",
                  }));
                  const csv =
                    "mal_id,title,year,season,pred_score,image_url\n" +
                    rows
                      .map((r) =>
                        [
                          r.mal_id,
                          `"${(r.title || "").replace(/"/g, '""')}"`,
                          r.year,
                          r.season,
                          r.pred_score,
                          `"${(r.image_url || "").replace(/"/g, '""')}"`,
                        ].join(",")
                      )
                      .join("\n");
                  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `predictions_${year}_${season}.csv`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="rounded-xl border border-border bg-card px-4 py-2 text-sm font-medium hover:bg-muted"
              >
                Export CSV
              </button>
            </div>
          </div>

          <p className="mt-2 text-sm text-muted-foreground">
            Live from your FastAPI endpoint:{" "}
            <a
              href={`${apiBase}/season/${year}/${season}/predictions`}
              className="underline"
              target="_blank"
              rel="noreferrer"
            >
              {`${apiBase}/season/${year}/${season}/predictions`}
            </a>
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="relative z-0 mx-auto max-w-7xl p-4">
        {/* Toolbar */}
        <div className="mb-4 flex items-center gap-3">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search title or MAL ID…"
            className="w-full rounded-2xl border border-input bg-background px-4 py-2.5 text-sm"
          />
          <button
            onClick={() => setSortByScore((v) => !v)}
            className="whitespace-nowrap rounded-2xl border border-border bg-card px-4 py-2.5 text-sm hover:bg-muted"
            title="Toggle sort"
          >
            {sortByScore ? "Sorted by score ↓" : "Original order"}
          </button>
        </div>

        {/* States */}
        {error && (
          <div className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600">
            Error: {error}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="h-72 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-border p-8 text-muted-foreground">
            No rows. Try Refresh, or adjust your filters.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {filtered.map((it, idx) => (
              <AnimeCard key={`${it.mal_id}-${idx}`} item={it} index={idx} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
