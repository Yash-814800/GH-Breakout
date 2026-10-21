/**
 * DuckDB-WASM, self-hosted (no CDN): the WASM binary and worker are bundled by Vite as hashed assets.
 * Only pages that call openDuck() ever download them. The views read same-origin Parquet over HTTP range requests.
 */
import * as duckdb from '@duckdb/duckdb-wasm';
import wasmUrl from '@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url';
import workerUrl from '@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url';
import { dataUrl } from './url';

export const VIEWS = {
  live_predictions: 'explorer/live_predictions.parquet',
  backtest_top100: 'explorer/oof_top100.parquet',
} as const;

let ready: Promise<{ db: duckdb.AsyncDuckDB; conn: duckdb.AsyncDuckDBConnection }> | null = null;

export function openDuck() {
  ready ??= (async () => {
    const worker = new Worker(workerUrl);
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(wasmUrl);
    const conn = await db.connect();
    for (const [view, file] of Object.entries(VIEWS)) {
      const href = new URL(dataUrl(file), location.href).toString();
      try {
        await conn.query(`CREATE VIEW ${view} AS SELECT * FROM read_parquet('${href}')`);
      } catch {
        // Hosts without range requests: load the whole file into memory instead.
        const buf = new Uint8Array(await (await fetch(href)).arrayBuffer());
        await db.registerFileBuffer(`${view}.parquet`, buf);
        await conn.query(`CREATE VIEW ${view} AS SELECT * FROM read_parquet('${view}.parquet')`);
      }
    }
    return { db, conn };
  })();
  ready.catch(() => (ready = null));
  return ready;
}
