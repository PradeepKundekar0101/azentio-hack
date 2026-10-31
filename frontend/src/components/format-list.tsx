/** File formats a page accepts, as a row of small tags with an optional note below. */
export function FormatList({ label, formats, note }: { label: string; formats: string[]; note?: string }) {
  return (
    <div className="mt-5 flex flex-col items-center gap-2">
      <ul aria-label={label} className="flex flex-wrap justify-center gap-1.5">
        {formats.map((format) => (
          <li
            key={format}
            className="inline-flex h-6 items-center rounded-md border bg-muted/50 px-2 text-xs font-medium text-muted-foreground"
          >
            {format}
          </li>
        ))}
      </ul>
      {note && <p className="text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}
