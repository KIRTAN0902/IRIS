import { Fragment, type ReactNode } from "react";
import { cn } from "@/lib/format";

/**
 * Minimal, safe markdown renderer for IRIS replies (no HTML injection: output
 * is React elements only). Supports headings, paragraphs, bullet and numbered
 * lists, block quotes, tables, horizontal rules, **bold**, *italic*, `code`.
 */
export function Markdown({ text, className }: { text: string; className?: string }) {
  return <div className={cn("space-y-2.5", className)}>{renderBlocks(text)}</div>;
}

function renderInline(text: string, keyBase = ""): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("**") || tok.startsWith("__")) {
      out.push(<strong key={key} className="font-semibold text-ink">{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`")) {
      out.push(
        <code key={key} className="rounded bg-ops-raised px-1 py-px font-[family-name:var(--font-mono)] text-[0.9em]">
          {tok.slice(1, -1)}
        </code>,
      );
    } else {
      out.push(<em key={key}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const isTableRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isTableSep = (l: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l);
const cells = (l: string) =>
  l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

function renderBlocks(text: string): ReactNode[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }

    // Heading
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const size = h[1].length <= 2 ? "text-[17px]" : "text-[15px]";
      blocks.push(
        <p key={k++} className={cn(size, "font-semibold text-ink pt-1")}>
          {renderInline(h[2], `h${k}`)}
        </p>,
      );
      i++;
      continue;
    }

    // Horizontal rule
    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      blocks.push(<hr key={k++} className="border-ops-line" />);
      i++;
      continue;
    }

    // Table
    if (isTableRow(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]));
      blocks.push(
        <div key={k++} className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr>
                {head.map((c, ci) => (
                  <th key={ci} className="border-b border-ops-line-bright px-2 py-1.5 text-left font-semibold text-ink">
                    {renderInline(c, `th${k}${ci}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>
                  {r.map((c, ci) => (
                    <td key={ci} className="border-b border-ops-line px-2 py-1.5 align-top text-ink-dim">
                      {renderInline(c, `td${k}${ri}${ci}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Lists (bullets or numbers, with simple nesting by indentation)
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: { depth: number; text: string }[] = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        const raw = lines[i];
        const depth = Math.min(2, Math.floor((raw.length - raw.trimStart().length) / 2));
        items.push({ depth, text: raw.trim().replace(/^([-*•]|\d+[.)])\s+/, "") });
        i++;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag
          key={k++}
          className={cn("space-y-1 pl-5", ordered ? "list-decimal" : "list-disc", "marker:text-ink-faint")}
        >
          {items.map((it, ii) => (
            <li key={ii} style={{ marginLeft: it.depth * 16 }}>
              {renderInline(it.text, `li${k}${ii}`)}
            </li>
          ))}
        </ListTag>,
      );
      continue;
    }

    // Block quote
    if (/^\s*>/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(
        <blockquote key={k++} className="border-l-2 border-ops-line-bright pl-3 text-ink-dim">
          {renderInline(quote.join(" "), `q${k}`)}
        </blockquote>,
      );
      continue;
    }

    // Paragraph: consecutive non-special lines
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,4})\s+/.test(lines[i]) &&
      !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i]) &&
      !/^\s*>/.test(lines[i]) &&
      !(isTableRow(lines[i]) && i + 1 < lines.length && isTableSep(lines[i + 1]))
    ) {
      para.push(lines[i++]);
    }
    blocks.push(
      <p key={k++}>
        {para.map((p, pi) => (
          <Fragment key={pi}>
            {pi > 0 && <br />}
            {renderInline(p, `p${k}${pi}`)}
          </Fragment>
        ))}
      </p>,
    );
  }
  return blocks;
}
