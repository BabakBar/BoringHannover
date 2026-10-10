export const KONAMI = [
  'ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown',
  'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight',
  'b', 'a',
] as const;

export const NINETY_SIX = ['9', '6'] as const;

const normalise = (key: string) => (key.length === 1 ? key.toLowerCase() : key);

/**
 * Advance through a key sequence. A wrong key falls back to the longest run of
 * recent keys that still starts the sequence, so an extra leading key never
 * costs a retry.
 */
export function sequenceStep(sequence: readonly string[], progress: number, key: string): number {
  const recent = [...sequence.slice(0, progress), normalise(key)];
  for (let length = Math.min(recent.length, sequence.length); length > 0; length--) {
    const tail = recent.slice(recent.length - length);
    if (tail.every((pressed, index) => pressed === sequence[index])) return length;
  }
  return 0;
}

export const konamiStep = (progress: number, key: string) => sequenceStep(KONAMI, progress, key);

export const toBinary = (value: number) => value.toString(2);

/** Ease-out count from 0 to `target`, for t in 0..1. */
export function countAt(t: number, target: number): number {
  const clamped = Math.min(1, Math.max(0, t));
  return Math.round(target * (1 - (1 - clamped) ** 3));
}
