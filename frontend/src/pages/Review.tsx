import { useReviewItems } from "../api/hooks";
import { ReviewItemCard } from "../components/ReviewItemCard";
import { StateBanner } from "../components/StateBanner";

/** Uncertain results, kept out of the main table (FR-037). */
export function Review() {
  const q = useReviewItems();
  return (
    <main className="page">
      <h1>Review</h1>
      <p className="lede">
        ApplyFlow puts anything it isn't sure about here instead of guessing: possible
        applications, emails that could match more than one application, offers and withdrawals,
        and contradictory updates.
      </p>
      {q.isLoading && <StateBanner variant="loading" title="Loading review items…" />}
      {q.isError && <StateBanner variant="error" title="Couldn't load review items." />}
      {q.data && q.data.items.length === 0 && (
        <StateBanner variant="empty" title="Nothing to review">
          New uncertain results will appear here after a scan or sync.
        </StateBanner>
      )}
      {q.data?.items.map((item) => <ReviewItemCard key={item.id} item={item} />)}
    </main>
  );
}
