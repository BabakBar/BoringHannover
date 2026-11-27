/**
 * Reader-facing labels for a published event status (#134). The exporter
 * publishes cancelled, postponed, rescheduled, sold_out, available or unknown.
 * Available and unknown carry no label: absent ticket information is not a
 * claim either way.
 */
const LABELS: Record<string, string> = {
  sold_out: 'Sold Out',
  cancelled: 'Cancelled',
  canceled: 'Cancelled',
  postponed: 'Postponed',
  rescheduled: 'Rescheduled',
};

export function eventStatusLabel(status: string | null | undefined): string | undefined {
  return status ? LABELS[status] : undefined;
}

/** Whether the listed date will not take place as announced. */
export function isCancelledStatus(status: string | null | undefined): boolean {
  return status === 'cancelled' || status === 'canceled';
}
