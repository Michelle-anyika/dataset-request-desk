import { Box, Pagination } from "@mantine/core";

/** Page numbers for a server-paged list, as a named navigation landmark. Hidden when one page holds it all. */
export function Pager({ label, page, pages, onChange }: { label: string; page: number; pages: number; onChange: (page: number) => void }) {
  if (pages <= 1) return null;
  return (
    <Box component="nav" aria-label={label}>
      <Pagination size="sm" value={Math.min(page, pages)} total={pages} onChange={onChange} />
    </Box>
  );
}
