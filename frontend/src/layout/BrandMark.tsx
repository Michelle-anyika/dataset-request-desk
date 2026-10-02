/** The product mark: a "D" on the brand red. Decorative, so hidden from screen readers. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="7" fill="var(--mantine-color-brand-filled)" />
      <path d="M10 9h7a7 7 0 0 1 0 14h-7z" fill="none" stroke="#fff" strokeWidth="3" />
    </svg>
  );
}
