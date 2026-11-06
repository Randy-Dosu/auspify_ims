/** Formatting helpers shared by tables and reports. */

// Change this if your business uses a different currency code.
export const CURRENCY = 'GHS'

const money = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: CURRENCY,
  minimumFractionDigits: 2,
})

export function formatMoney(value) {
  return money.format(Number(value) || 0)
}

export function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value) || 0)
}

/** "2026-11-06T09:58:45Z" -> local date + time, e.g. "06/11/2026, 09:58". */
export function formatDateTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}
