import { readFileSync } from 'fs';

/**
 * Parses a CSV line into cells, honouring quoted values.
 */
export function parseCsvLine(line: string, delimiter = ','): string[] {
  const cells: string[] = [];
  let current = '';
  let quoted = false;
  for (const ch of line) {
    if (ch === '"') {
      quoted = !quoted;
    } else if (ch === delimiter && !quoted) {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells;
}

export class ReportLoader {
  constructor(private readonly path: string) {}

  /** Loads the report and returns rows without the header line. */
  load(): string[][] {
    const text = readFileSync(this.path, 'utf-8');
    return text.split('\n').slice(1).filter(Boolean).map((line) => parseCsvLine(line));
  }
}

export const sumColumn = (rows: string[][], index: number): number =>
  rows.reduce((acc, row) => acc + Number.parseFloat(row[index] ?? '0'), 0);
