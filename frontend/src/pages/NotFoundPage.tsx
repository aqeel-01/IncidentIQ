import { Link } from "react-router-dom";

import { paths } from "@/routes/paths";

export function NotFoundPage() {
  return (
    <section className="page">
      <div className="page__intro">
        <p className="eyebrow">404</p>
        <h1>Page not found</h1>
        <p className="lede">That route is not part of the current foundation.</p>
      </div>
      <Link className="button" to={paths.home}>
        Return home
      </Link>
    </section>
  );
}
