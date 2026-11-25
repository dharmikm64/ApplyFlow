import { useSearchParams } from "react-router-dom";
import { StateBanner } from "../components/StateBanner";

const ERRORS: Record<string, string> = {
  not_allowed:
    "Access is limited to approved test accounts. Ask the ApplyFlow owner to add your Google account.",
  signin_cancelled: "Sign-in was cancelled.",
  signin_failed: "Sign-in failed. Please try again.",
  signin_required: "Please sign in first.",
};

export function SignIn() {
  const [params] = useSearchParams();
  const error = params.get("error");
  return (
    <main className="signin">
      <h1>ApplyFlow</h1>
      <p className="lede">
        Turn your recruiting emails into an application tracker: one row per application, kept up
        to date from your inbox.
      </p>
      {error && (
        <StateBanner variant="error" title="Couldn't sign you in">
          {ERRORS[error] ?? "Something went wrong. Please try again."}
        </StateBanner>
      )}
      <a className="button button--primary" href="/auth/login">
        Sign in with Google
      </a>
      <p className="fineprint">
        Signing in does not give ApplyFlow access to your email. You'll be asked separately, and
        only for read-only access.
      </p>
    </main>
  );
}
