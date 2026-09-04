import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";

/**
 * Testing Library waits 1s by default for `findBy*` and `waitFor`. Several of
 * these specs type into half a dozen fields before asserting, which comfortably
 * exceeds that on a loaded machine — the suite then fails for lack of time
 * rather than for a defect. Give the async helpers room; a genuinely absent
 * element still fails, only a few seconds later.
 */
configure({ asyncUtilTimeout: 5000 });

/**
 * This jsdom build exposes a `localStorage` object without its methods, so the
 * token store (and anything else using Web Storage) would fail under test.
 * Install a spec-compliant in-memory implementation instead.
 */
class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  Object.defineProperty(globalThis, name, {
    value: new MemoryStorage(),
    writable: true,
    configurable: true,
  });
}
