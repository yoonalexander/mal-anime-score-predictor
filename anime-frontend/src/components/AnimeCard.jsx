import { useMemo } from "react";

function scoreToBadge(score) {
  if (score >= 8.5) return "bg-green-600/10 text-green-600 ring-1 ring-inset ring-green-600/30";
  if (score >= 8.0) return "bg-emerald-600/10 text-emerald-600 ring-1 ring-inset ring-emerald-600/30";
  if (score >= 7.5) return "bg-lime-600/10 text-lime-700 ring-1 ring-inset ring-lime-700/30";
  if (score >= 7.0) return "bg-amber-500/10 text-amber-700 ring-1 ring-inset ring-amber-600/30";
  if (score >= 6.5) return "bg-orange-500/10 text-orange-700 ring-1 ring-inset ring-orange-600/30";
  return "bg-red-500/10 text-red-600 ring-1 ring-inset ring-red-600/30";
}

// pick the fastest cover URL (small webp/jpg if available)
function pickCover(u) {
  if (u?.images) {
    return (
      u.images?.webp?.small_image_url ||
      u.images?.jpg?.small_image_url ||
      u.images?.webp?.image_url ||
      u.images?.jpg?.image_url ||
      null
    );
  }
  return u || null; // already a string
}

export default function AnimeCard({ item, index }) {
  const scoreClass = useMemo(() => scoreToBadge(item.pred_score ?? 0), [item.pred_score]);
  const cover = pickCover(item.image_url);

  return (
    <article className="group relative z-0 overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition hover:shadow-md">
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
          />
        ) : (
          <div className="h-full w-full animate-pulse bg-muted" />
        )}
      </div>

      <div className="flex flex-col gap-2 p-4">
        <h3 className="text-base/5 font-medium text-foreground line-clamp-2">{item.title}</h3>
        <div className="flex items-center justify-between">
          <a
            href={`https://myanimelist.net/anime/${item.mal_id}`}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-primary/80 hover:text-primary hover:underline"
          >
            MAL: {item.mal_id}
          </a>
          <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${scoreClass}`}>
            {item.pred_score?.toFixed(2)}
          </span>
        </div>
      </div>
    </article>
  );
}
