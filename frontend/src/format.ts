import dayjs from 'dayjs'

const money = new Intl.NumberFormat('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const formatMoney = (value: number, currency = 'PLN') =>
  `${money.format(value)}${currency === 'PLN' ? ' zł' : ` ${currency}`}`

export const formatDate = (value: string | null | undefined) =>
  value ? dayjs(value).format('DD-MM-YYYY') : ''

export const monthToDate = (month: string) => `${month}-01`
export const dateToMonth = (value: string) => value.slice(0, 7)

export const isCorrection = (invoiceType: string) => invoiceType.toUpperCase().startsWith('KOR')
