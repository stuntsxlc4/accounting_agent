import dayjs from 'dayjs'

const money = new Intl.NumberFormat('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const formatMoney = (value: number, currency = 'PLN') =>
  `${money.format(value)}${currency === 'PLN' ? ' zł' : ` ${currency}`}`

export const formatDate = (value: string | null | undefined) =>
  value ? dayjs(value).format('DD-MM-YYYY') : ''

export const monthToDate = (month: string) => `${month}-01`
export const dateToMonth = (value: string) => value.slice(0, 7)

export const isCorrection = (invoiceType: string) => invoiceType.toUpperCase().startsWith('KOR')

export const formatDateTime = (value: string | null | undefined) =>
  value ? dayjs(value).format('DD-MM-YYYY, HH:mm') : ''

export const formatSize = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`

/** Ostatnie elementy ścieżki, np. "Faktury ZAKUPOWE › Sierpień 2026". */
export const shortPath = (path: string, parts = 2) => {
  const segments = path.split(/[\\/]/).filter(Boolean)
  return (segments.length > parts ? '… › ' : '') + segments.slice(-parts).join(' › ')
}
