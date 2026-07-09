import { useMemo, useState } from "react";

function scoreToBadge(score) {
  if (score >= 8.5) return "bg-green-600/10 text-green-600 ring-1 ring-inset ring-green-600/30";
  if (score >= 8.0) return "bg-emerald-600/10 text-emerald-600 ring-1 ring-inset ring-emerald-600/30";
  if (score >= 7.5) return "bg-lime-600/10 text-lime-700 ring-1 ring-inset ring-lime-700/30";
  if (score >= 7.0) return "bg-amber-500/10 text-amber-700 ring-1 ring-inset ring-amber-600/30";
  if (score >= 6.5) return "bg-orange-500/10 text-orange-700 ring-1 ring-inset ring-orange-600/30";
  return "bg-red-500/10 text-red-600 ring-1 ring-inset ring-red-600/30";
}

// image_url is now always a plain string (committed in the JSON artifact).
function pickCover(url) {
  if (!url) return null;
  return typeof url === "string" ? url : null;
}

export default function AnimeCard({ item, index }) {
  const score = item.pred_score ?? 0;
  const scoreClass = useMemo(() => scoreToBadge(score), [score]);
  const cover = pickCover(item.image_url);
  const [expanded, setExpanded] = useState(false);

  const genres = (item.genres || []).slice(0, 4);
  const hasRange =
    item.pred_low != null && item.pred_high != null && item.pred_low !== item.pred_high;

  return (
    <article className="group relative z-0 flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition hover:shadow-md">
      <div className="aspect-[3/4] w-full overflow-hidden bg-muted">
        {cover ? (
          <img
            src={cover}
            alt={item.title}
            loading={index < 8 ? "eager" : "lazy"}
            decoding="async"
            width={300}
            height={400}
            sizes="(min-width:1024px) 25vw, (min-width:768px) 33vw, 50vw"
            className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.03]"
            // Fall back to a muted placeholder if the CDN image errors.
            onError={(e) => {
              e.currentTarget.style.visibility = "hidden";
            }}
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-muted text-xs text-muted-foreground">
            No cover
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-base/5 font-medium text-foreground line-clamp-2">{item.title}</h3>

        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          {item.studio && (
            <span className="rounded-md bg-muted px-1.5 py-0.5 font-medium text-foreground/80">
              {item.studio}
            </span>
          )}
          {item.type && <span>{item.type}</span>}
          {item.episodes != null && <span>· {item.episodes} ep</span>}
          {item.source && item.source !== "unknown" && <span>· {item.source}</span>}
        </div>

        {genres.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {genres.map((g) => (
              <span
                key={g}
                className="rounded-full bg-secondary px-2 py-0.5 text-[10px] font-medium text-secondary-foreground"
              >
                {g}
              </span>
            ))}
          </div>
        )}

        {item.synopsis && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-left text-xs text-muted-foreground/80 hover:text-foreground"
          >
            <span className={expanded ? "" : "line-clamp-2"}>{item.synopsis.replace(/<br\s*\/?>/gi, " ")}</span>
            <span className="ml-1 underline">{expanded ? "less" : "more"}</span>
          </button>
        )}

        <div className="mt-auto flex items-center justify-between pt-2">
          <a
            href={item.mal_url || `https://myanimelist.net/anime/${item.mal_id}`}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-primary/80 hover:text-primary hover:underline"
          >
            MAL: {item.mal_id}
          </a>
          <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${scoreClass}`}>
            {score.toFixed(2)}
          </span>
        </div>

        {hasRange && (
          <div className="text-[10px] text-muted-foreground/70">
            est. {item.pred_low?.toFixed(1)} – {item.pred_high?.toFixed(1)}
          </div>
        )}
      </div>
    </article>
  );
}
