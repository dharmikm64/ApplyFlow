import { Link } from "react-router-dom";

/** Plain-language explanation shown BEFORE Google's consent screen (FR-002). */
export function ConnectGmail() {
  return (
    <main className="page">
      <div className="card" style={{ maxWidth: 720 }}>
        <h1>Connect Gmail (read-only)</h1>
        <p className="lede">
          ApplyFlow builds your application table from recruiting emails. Here's exactly what that
          means before Google asks you to approve.
        </p>

        <h2>What ApplyFlow reads</h2>
        <ul>
          <li>
            For emails in the date range you choose: the sender, subject, date, and message text.
          </li>
          <li>Spam and Trash are skipped. Archived emails are included.</li>
        </ul>

        <h2>What ApplyFlow stores</h2>
        <ul>
          <li>Extracted details: company, position, application date, and status.</li>
          <li>
            For recruiting emails only: the sender, subject, date, and a short excerpt (a sentence
            or two) as evidence you can check.
          </li>
          <li>Full email bodies are never stored.</li>
        </ul>

        <h2>What ApplyFlow never does</h2>
        <ul>
          <li>It never sends, deletes, labels, archives, or changes any email.</li>
          <li>
            Email content is analyzed only within ApplyFlow and is never shared with third parties.
          </li>
        </ul>

        <h2>Staying in control</h2>
        <p>
          You can disconnect Gmail at any time in <Link to="/settings">Settings</Link>, which revokes
          access and deletes the stored credentials. Your table is kept unless you delete it too.
        </p>
        <p className="fineprint">
          While ApplyFlow is in testing, Google shows an "unverified app" warning and limits access
          to 7 days, so you may need to reconnect about once a week.
        </p>

        <div className="row">
          <a className="button button--primary" href="/auth/gmail/connect">
            Continue to Google
          </a>
          <Link className="button" to="/">
            Not now
          </Link>
        </div>
      </div>
    </main>
  );
}
