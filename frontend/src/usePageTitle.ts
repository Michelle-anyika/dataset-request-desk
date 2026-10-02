import { useEffect } from "react";

/** Sets the browser tab title, which is also what screen readers announce on navigation. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · Dataset Request Desk`;
  }, [title]);
}
