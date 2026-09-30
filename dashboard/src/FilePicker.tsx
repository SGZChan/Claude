import { useRef, useState } from "react";
import { api } from "./api";

export interface Source { name: string; text: string; lines: number }

/** Read a file as text. Handles UTF-8 (with/without BOM) and the UTF-16 that Windows PowerShell writes. */
export async function readFileText(f: File): Promise<string> {
  const b = new Uint8Array(await f.arrayBuffer());
  if (b[0] === 0xff && b[1] === 0xfe) return new TextDecoder("utf-16le").decode(b.subarray(2));
  if (b[0] === 0xfe && b[1] === 0xff) return new TextDecoder("utf-16be").decode(b.subarray(2));
  const s = new TextDecoder("utf-8").decode(b);
  return s.charCodeAt(0) === 0xfeff ? s.slice(1) : s;
}

const countLines = (t: string) => t.split("\n").filter((l) => l.trim()).length;

/** Drop zone + file chooser. Accepts ANY file type (no `accept` filter, so .jsonl is never greyed out) and many files at once. */
export default function FilePicker({ onLoaded, multiple = true, label = "Drop files here, or click to choose", maxBytes = 5_000_000 }: {
  onLoaded: (sources: Source[]) => void; multiple?: boolean; label?: string; maxBytes?: number;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  const load = async (list: FileList | File[]) => {
    const ok: Source[] = [], bad: string[] = [];
    for (const f of Array.from(list).slice(0, multiple ? 50 : 1)) {
      if (f.size > maxBytes) { bad.push(`${f.name}: over ${Math.round(maxBytes / 1e6)} MB`); continue; }
      const text = await readFileText(f);
      if (text.includes("\u0000")) { bad.push(`${f.name}: doesn't look like a text file`); continue; }
      ok.push({ name: f.name, text, lines: countLines(text) });
    }
    setProblems(bad);
    if (ok.length) onLoaded(ok);
    if (input.current) input.current.value = ""; // allow picking the same file again
  };

  return (
    <div>
      <div className={`dropzone ${over ? "over" : ""}`} role="button" tabIndex={0} aria-label={label}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); load(e.dataTransfer.files); }}>
        <span>📄 {label}</span>
        <input ref={input} type="file" multiple={multiple} className="sr-file" aria-label="Choose files" tabIndex={-1}
          onClick={(e) => e.stopPropagation()} onChange={(e) => e.target.files && load(e.target.files)} />
      </div>
      {problems.map((p) => <div key={p} className="err" role="alert" style={{ fontSize: 12 }}>{p}</div>)}
    </div>
  );
}

export function SourceChips({ sources, onRemove }: { sources: Source[]; onRemove: (i: number) => void }) {
  if (!sources.length) return null;
  return (
    <div className="chips" style={{ margin: "8px 0" }}>
      {sources.map((s, i) => (
        <span key={s.name + i} className="chip">{s.name} · {s.lines} line{s.lines === 1 ? "" : "s"}
          <button className="link" style={{ marginLeft: 6 }} onClick={() => onRemove(i)} aria-label={`Remove ${s.name}`}>✕</button></span>
      ))}
    </div>
  );
}

/** POST each source separately (formats can differ per file) and collect per-source results. */
export async function postEach(url: string, sources: Source[], extra: Record<string, unknown>, field: string) {
  const out: { name: string; res?: any; error?: string }[] = [];
  for (const s of sources) {
    try { out.push({ name: s.name, res: await api.post(url, { ...extra, [field]: s.text }) }); }
    catch (e: any) { out.push({ name: s.name, error: e.message }); }
  }
  return out;
}
