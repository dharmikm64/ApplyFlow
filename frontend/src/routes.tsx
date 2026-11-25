import { Link, NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAccountActions, useMe, useReviewItems } from "./api/hooks";
import { StateBanner } from "./components/StateBanner";
import { ConnectGmail } from "./pages/ConnectGmail";
import { Dashboard } from "./pages/Dashboard";
import { Review } from "./pages/Review";
import { Settings } from "./pages/Settings";
import { SignIn } from "./pages/SignIn";

function Header({ email }: { email: string }) {
  const { signOut } = useAccountActions();
  const review = useReviewItems();
  const navigate = useNavigate();
  const pending = review.data?.pendingCount ?? 0;
  return (
    <header className="app-header">
      <Link to="/" className="brand">
        ApplyFlow
      </Link>
      <nav aria-label="Main">
        <NavLink to="/" end>
          Applications
        </NavLink>
        <NavLink to="/review">
          Review
          {pending > 0 && (
            <span className="badge" aria-label={`${pending} items to review`}>
              {pending}
            </span>
          )}
        </NavLink>
        <NavLink to="/settings">Settings</NavLink>
      </nav>
      <div className="app-header__user">
        <span>{email}</span>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => signOut.mutate(undefined, { onSuccess: () => navigate("/") })}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}

export function AppRoutes() {
  const me = useMe();
  if (me.isLoading) {
    return (
      <main className="page">
        <StateBanner variant="loading" title="Loading ApplyFlow…" />
      </main>
    );
  }
  if (me.isError) {
    return (
      <main className="page">
        <StateBanner variant="error" title="ApplyFlow is unavailable">
          The server could not be reached. Try again in a moment.
        </StateBanner>
      </main>
    );
  }
  if (!me.data) {
    return (
      <Routes>
        <Route path="*" element={<SignIn />} />
      </Routes>
    );
  }
  return (
    <>
      <Header email={me.data.user.email} />
      <Routes>
        <Route path="/" element={<Dashboard me={me.data} />} />
        <Route path="/connect" element={<ConnectGmail />} />
        <Route path="/review" element={<Review />} />
        <Route path="/settings" element={<Settings me={me.data} />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}
