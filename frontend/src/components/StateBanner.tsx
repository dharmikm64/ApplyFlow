import type { ReactNode } from "react";

export type BannerVariant = "info" | "loading" | "empty" | "error" | "reconnect" | "success";

interface Props {
  variant: BannerVariant;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

/** Accessible status/alert banner for loading, empty, failed, and reconnect states (FR-032). */
export function StateBanner({ variant, title, children, action }: Props) {
  const isAlert = variant === "error" || variant === "reconnect";
  return (
    <section
      className={`banner banner--${variant}`}
      role={isAlert ? "alert" : "status"}
      aria-live={isAlert ? "assertive" : "polite"}
      data-testid={`banner-${variant}`}
    >
      <div className="banner__body">
        <strong className="banner__title">{title}</strong>
        {children && <div className="banner__text">{children}</div>}
      </div>
      {action && <div className="banner__action">{action}</div>}
    </section>
  );
}
