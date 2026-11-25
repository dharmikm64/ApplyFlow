import type { ApplicationRow } from "../api/types";
import { STATUS_LABELS } from "../api/types";

interface Props {
  items: ApplicationRow[];
  order: "asc" | "desc";
  onToggleSort: () => void;
  onOpen: (id: string) => void;
  caption: string;
}

function Unknown() {
  return <span className="unknown">Unknown</span>;
}

/** Main table: exactly four data columns (FR-030). */
export function ApplicationsTable({ items, order, onToggleSort, onOpen, caption }: Props) {
  return (
    <div className="table-wrap">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Company</th>
            <th scope="col">Position</th>
            <th scope="col" aria-sort={order === "asc" ? "ascending" : "descending"}>
              <button type="button" className="sort-button" onClick={onToggleSort}>
                Date Applied {order === "asc" ? "▲" : "▼"}
                <span className="visually-hidden">
                  , sorted {order === "asc" ? "oldest first" : "newest first"}; activate to reverse
                </span>
              </button>
            </th>
            <th scope="col">Application Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((a) => (
            <tr
              key={a.id}
              tabIndex={0}
              onClick={() => onOpen(a.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(a.id);
                }
              }}
              aria-label={`Open details for ${a.company ?? "unknown company"}, ${a.position ?? "unknown position"}`}
            >
              <td>
                {a.company ?? <Unknown />}
                {a.beforeCycle && <span className="tag">Before current cycle</span>}
                {a.pendingReview && <span className="tag">Needs review</span>}
              </td>
              <td>{a.position ?? <Unknown />}</td>
              <td>
                {a.dateApplied ? (
                  <>
                    {a.dateApplied}
                    {a.dateAppliedSource === "estimated" && (
                      <span className="est" title="Estimated from the confirmation email's date">
                        est.
                      </span>
                    )}
                  </>
                ) : (
                  <Unknown />
                )}
              </td>
              <td>
                <span className={`status status--${a.status}`}>{STATUS_LABELS[a.status]}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
