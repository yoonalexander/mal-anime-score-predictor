import { useEffect, useMemo, useState } from "react";
import AnimeCard from "./components/AnimeCard";
import BackgroundParticles from "./components/BackgroundParticles";

// Predictions are committed as static JSON under /public/predictions/.
// The frontend fetches them from the same origin, so no backend is required
// in production (works on Vercel static hosting).
const PREDICTIONS_BASE = import.meta.env.BASE_URL
  ? `${import.meta.env.BASE_URL}predictions/`
  : "/predictions/";

// Fallback list if index.json fails to load (e.g. during local dev before export).
const FALLBACK_SEASONS = [
  { year: 2026, season: "summer", label: "Summer 2026", file: "2026-summer.json", count: 0 },
  { year: 2025, season: "fall", label: "Fall 2025", file: "2025-fall.json", count: 0 },
];

async function fetchSeasonList() {
  try {
    const res = await fetch(`${PREDICTIONS_BASE}index.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return FALLBACK_SEASONS;
  }
}

async function fetchPredictions(file) {
  const res = await fetch(`${PREDICTIONS_BASE}${file}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export default function AnimePredictionsApp() {
  const [seasons, setSeasons] = useState(FALLBACK_SEASONS);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState([]);

  const [query, setQuery] = useState("");
  const [sortByScore, setSortByScore] = useState(true);

  // Load the list of available seasons once.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const list = await fetchSeasonList();
      if (cancelled) return;
      setSeasons(list);
      if (list.length && !selected) {
        setSelected(`${list[0].year}:${list[0].season}`);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load predictions whenever the selected season changes.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;

    (async () => {
      setError("");
      setLoading(true);
      try {
        const entry = seasons.find(
          (s) => `${s.year}:${s.season}` === selected
        );
        if (!entry) throw new Error("Selected season not found");
        const data = await fetchPredictions(entry.file);
        if (!cancelled) setItems(data);
      } catch (e) {
        console.error(e);
        if (!cancelled) {
          setError(e?.message || "Failed to load predictions");
          setItems([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selected, seasons]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = !q
      ? items
      : items.filter(
          (r) =>
            r.title?.toLowerCase().includes(q) ||
            String(r.mal_id).includes(q) ||
            (r.studio || "").toLowerCase().includes(q)
        );

    if (sortByScore) {
      rows = rows.slice().sort((a, b) => (b.pred_score ?? 0) - (a.pred_score ?? 0));
    }
    return rows;
  }, [items, query, sortByScore]);

  const currentEntry = seasons.find((s) => `${s.year}:${s.season}` === selected);

  return (
    <div className="relative min-h-screen isolate">
      <BackgroundParticles />

      {/* Header / nav */}
      <header className="sticky top-0 z-50 bg-white/70 dark:bg-slate-900/70 backdrop-blur">
        <div className="mb-6 rounded-3xl border border-border bg-gradient-to-b from-background to-muted p-6">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold">MAL Anime Score Predictions</h1>

            <div className="ml-auto flex flex-wrap items-center gap-2">
              <select
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                className="w-44 rounded-xl border border-input bg-background px-3 py-2 text-sm"
              >
                {seasons.map((s) => (
                  <option key={`${s.year}:${s.season}`} value={`${s.year}:${s.season}`}>
                    {s.label}
                  </option>
                ))}
              </select>

              <button
                onClick={() => setSelected(selected + "")}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:opacity-90"
                title="Refresh"
              >
                Refresh
              </button>

              <button
                onClick={() => {
                  const rows = filtered.map((r) => ({
                    mal_id: r.mal_id,
                    title: r.title,
                    year: r.year,
                    season: r.season,
                    pred_score: r.pred_score,
                    pred_low: r.pred_low,
                    pred_high: r.pred_high,
                    studio: r.studio,
                    image_url: r.image_url || "",
                  }));
                  const header =
                    "mal_id,title,year,season,pred_score,pred_low,pred_high,studio,image_url\n";
                  const csv =
                    header +
                    rows.map((r) =>
                      [
                        r.mal_id,
                        `"${(r.title || "").replace(/"/g, '""')}"`,
                        r.year,
                        r.season,
                        r.pred_score,
                        r.pred_low,
                        r.pred_high,
                        `"${(r.studio || "").replace(/"/g, '""')}"`,
                        `"${(r.image_url || "").replace(/"/g, '""')}"`,
                      ].join(",")
                    ).join("\n");
                  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = `predictions_${currentEntry?.year}_${currentEntry?.season}.csv`;
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
            {currentEntry
              ? `${currentEntry.label} — ${currentEntry.count || filtered.length} titles, predicted from Jikan/AniList metadata.`
              : "Select a season to view predictions."}
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
            placeholder="Search title, MAL ID, or studio..."
            className="w-full rounded-2xl border border-input bg-background px-4 py-2.5 text-sm"
          />
          <button
            onClick={() => setSortByScore((v) => !v)}
            className="whitespace-nowrap rounded-2xl border border-border bg-card px-4 py-2.5 text-sm hover:bg-muted"
            title="Toggle sort"
          >
            {sortByScore ? "Sorted by score down" : "Original order"}
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
            No rows. Try a different season or adjust your filters.
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
