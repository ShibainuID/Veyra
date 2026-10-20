/** The VEYRA mark: a small solid ear tag with its punched hole, drawn to sit on the black shell. */
export function TagLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 28 34" className={className} aria-hidden="true" focusable="false">
      <path
        d="M10 1.5H18Q21.5 1.5 22.2 5C22.8 8.2 26.5 8.6 26.5 14V25.5Q26.5 32.5 19.5 32.5H8.5Q1.5 32.5 1.5 25.5V14C1.5 8.6 5.2 8.2 5.8 5Q6.5 1.5 10 1.5ZM17 7.5A3 3 0 1 0 11 7.5A3 3 0 1 0 17 7.5Z"
        fill="var(--tag)"
        fillRule="evenodd"
      />
    </svg>
  );
}
