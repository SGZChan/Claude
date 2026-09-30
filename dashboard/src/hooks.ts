import { useCallback, useEffect, useRef, useState } from "react";
import { api, Json } from "./api";

/** Fetch a URL and poll it. */
export function useApi<T = Json>(url: string, pollMs = 0): [T | null, () => void, string] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const alive = useRef(true);
  const load = useCallback(() => {
    api.get(url).then((d) => alive.current && (setData(d), setErr(""))).catch((e) => alive.current && setErr(String(e.message)));
  }, [url]);
  useEffect(() => {
    alive.current = true;
    load();
    const t = pollMs ? setInterval(load, pollMs) : undefined;
    return () => { alive.current = false; t && clearInterval(t); };
  }, [load, pollMs]);
  return [data, load, err];
}
