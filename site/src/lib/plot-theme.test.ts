import { afterEach, describe, expect, it, vi } from 'vitest';
import { HEIGHTS, baseOptions, resolveTokens } from './plot-theme';

const fake = (vars: Record<string, string>) =>
  vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: (name: string) => ` ${vars[name] ?? ''} ` }));
afterEach(() => vi.unstubAllGlobals());

describe('resolveTokens', () => {
  it('reads the CSS custom properties and trims them', () => {
    fake({ '--accent': '#111111', '--ink-3': '#222222', '--font-ui': 'Test Sans', '--raised': '#333333' });
    const t = resolveTokens({} as Element);
    expect(t.accent).toBe('#111111');
    expect(t.ink3).toBe('#222222');
    expect(t.raised).toBe('#333333');
    expect(t.font).toBe('Test Sans');
  });

  it('returns the new values after a theme switch', () => {
    fake({ '--accent': '#4650c4' });
    expect(resolveTokens({} as Element).accent).toBe('#4650c4');
    fake({ '--accent': '#929bf2' });
    expect(resolveTokens({} as Element).accent).toBe('#929bf2');
  });
});

describe('baseOptions', () => {
  const tokens = { font: 'F', ink3: 'g' } as unknown as ReturnType<typeof resolveTokens>;
  it('uses the spec margins, y-only grid and no axis labels', () => {
    const o = baseOptions(tokens, 600);
    expect(o).toMatchObject({ width: 600, height: HEIGHTS.standard, marginTop: 8, marginBottom: 28 });
    expect(o.y.grid).toBe(true);
    expect(o.y.ticks).toBe(4);
    expect(o.x.label).toBeNull();
    expect(o.style.background).toBe('transparent');
  });
  it('never returns a width under 160 px and formats ticks compactly', () => {
    expect(baseOptions(tokens, 40).width).toBe(160);
    expect(baseOptions(tokens, 600).y.tickFormat(2912)).toBe('2.9k');
  });
  it('has the three chart heights from the spec', () => {
    expect(HEIGHTS).toEqual({ sparkline: 64, standard: 240, hero: 280 });
  });
});
