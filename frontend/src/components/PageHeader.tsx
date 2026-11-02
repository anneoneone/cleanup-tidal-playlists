import { type ReactNode, useEffect } from "react";

export function PageHeader({
  title,
  description,
  actions,
  documentTitle,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Text for the browser tab; defaults to `title` when it is a string. */
  documentTitle?: string;
}) {
  const tabTitle = documentTitle ?? (typeof title === "string" ? title : undefined);
  useEffect(() => {
    if (tabTitle) document.title = `${tabTitle} · Cratekeeper`;
  }, [tabTitle]);

  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight break-words sm:text-2xl">
          {title}
        </h1>
        {description && <div className="mt-1 text-sm text-muted">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
